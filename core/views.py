from django.conf import settings
from django.contrib import messages
from django.contrib.auth import get_user_model
from django.core.exceptions import ObjectDoesNotExist
from django.core.exceptions import ValidationError
from django.contrib.auth.decorators import login_required
from django.contrib.auth.mixins import LoginRequiredMixin
from django.shortcuts import render, get_object_or_404
from django.views.generic import ListView, DetailView, View
from django.shortcuts import redirect
from django.urls import reverse
from urllib.parse import urlencode
from django.utils.decorators import method_decorator
from django.utils import timezone
from django.core.paginator import Paginator
from django.db import transaction
from django.db.models import F, Q, Avg, Count, Exists, OuterRef
from django.db.models.functions import Coalesce
from decimal import Decimal, InvalidOperation
from .forms import CheckoutForm, CouponForm, RefundForm, ProfileForm
from .models import Item, ItemVariant, OrderItem, Order, BillingAddress, Payment, Coupon, Refund, Category, UserProfile, Wishlist, Review, OrderStatusHistory, StockMovement
from .order_workflow import transition_order_status
from .notifications import send_order_status_email
from django.http import HttpResponseRedirect
from django.shortcuts import render
from django.views.decorators.http import require_POST
# Create your views here.
import random
import string


def _clean_price_filter(value):
    if not value:
        return None
    try:
        amount = Decimal(value)
    except (InvalidOperation, TypeError, ValueError):
        return None
    if not amount.is_finite() or amount < 0:
        return None
    return amount


def create_ref_code():
    for _ in range(10):
        code = ''.join(random.choices(string.ascii_lowercase + string.digits, k=20))
        if not Order.objects.filter(ref_code=code).exists():
            return code
    raise RuntimeError('Could not generate a unique order reference.')


class PaymentView(LoginRequiredMixin, View):
    """Keep the old card URL working while the shop currently accepts COD only."""
    def get(self, request, *args, **kwargs):
        messages.info(request, 'This shop currently accepts cash on delivery. Complete your order at checkout.')
        return redirect('core:checkout')

    def post(self, request, *args, **kwargs):
        messages.info(request, 'This shop currently accepts cash on delivery. Complete your order at checkout.')
        return redirect('core:checkout')


class HomeView(ListView):
    template_name = "index.html"
    context_object_name = 'items'
    # Keep the homepage focused and lightweight; the Shop page remains paginated
    # and provides access to the full active catalog.
    paginate_by = 8

    def get_queryset(self):
        active_variants = ItemVariant.objects.filter(item_id=OuterRef('pk'), is_active=True)
        qs = Item.objects.filter(is_active=True).prefetch_related('variants').annotate(
            home_has_variant=Exists(active_variants),
            home_has_stock=Exists(active_variants.filter(stock_quantity__gt=0)) | Q(
                stock_quantity__gt=0,
                variants__isnull=True,
            ),
        ).distinct()
        q = self.request.GET.get('q')
        if q:
            qs = qs.filter(title__icontains=q)
        return qs.order_by('-pk')


class OrderSummaryView(LoginRequiredMixin, View):
    def get(self, *args, **kwargs):
        try:
            order = Order.objects.get(user=self.request.user, ordered=False)
            context = {
                'object': order
            }
            return render(self.request, 'order_summary.html', context)
        except ObjectDoesNotExist:
            messages.warning(self.request, "You do not have an active order!")
            return redirect("/")


class ShopView(ListView):
    model = Item
    paginate_by = 6
    template_name = "shop.html"

    def get_queryset(self):
        qs = Item.objects.filter(is_active=True).select_related('category').prefetch_related('variants').annotate(
            average_rating=Avg('reviews__rating'),
            review_count=Count('reviews', distinct=True),
            effective_price=Coalesce('discount_price', 'price'),
        )
        q = self.request.GET.get('q')
        if q:
            qs = qs.filter(Q(title__icontains=q) | Q(description_short__icontains=q) | Q(description_long__icontains=q) | Q(category__title__icontains=q))
        category = self.request.GET.get('category')
        if category:
            qs = qs.filter(category__slug=category)
        min_price = _clean_price_filter(self.request.GET.get('min_price'))
        max_price = _clean_price_filter(self.request.GET.get('max_price'))
        if min_price is not None:
            qs = qs.filter(effective_price__gte=min_price)
        if max_price is not None:
            qs = qs.filter(effective_price__lte=max_price)
        size = self.request.GET.get('size', '').strip()
        color = self.request.GET.get('color', '').strip()
        in_stock = self.request.GET.get('in_stock') == '1'
        variant_match = ItemVariant.objects.filter(item_id=OuterRef('pk'), is_active=True)
        if size:
            variant_match = variant_match.filter(size=size)
        if color:
            variant_match = variant_match.filter(color=color)
        if size or color:
            qs = qs.annotate(_matching_variant=Exists(variant_match.filter(stock_quantity__gt=0))).filter(_matching_variant=True)
        elif in_stock:
            available_variant = ItemVariant.objects.filter(item_id=OuterRef('pk'), is_active=True, stock_quantity__gt=0)
            any_variant = ItemVariant.objects.filter(item_id=OuterRef('pk'), is_active=True)
            qs = qs.annotate(_has_stock=Exists(available_variant), _has_variant=Exists(any_variant)).filter(Q(_has_stock=True) | Q(_has_variant=False, stock_quantity__gt=0))
        sort = self.request.GET.get('sort', 'newest')
        ordering = {
            'price_asc': ('effective_price', 'title'),
            'price_desc': ('-effective_price', 'title'),
            'name': ('title',),
            'rating': ('-average_rating', '-review_count', 'title'),
            'newest': ('-id',),
        }
        return qs.order_by(*ordering.get(sort, ordering['newest']))

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['categories'] = Category.objects.filter(is_active=True).order_by('title')
        context['active_filters'] = self.request.GET
        context['available_sizes'] = ItemVariant.objects.filter(is_active=True, item__is_active=True).values_list('size', flat=True).distinct().order_by('size')
        context['available_colors'] = ItemVariant.objects.filter(is_active=True, item__is_active=True).values_list('color', flat=True).distinct().order_by('color')
        return context


class ItemDetailView(DetailView):
    model = Item
    template_name = "product-detail.html"

    def get_queryset(self):
        return Item.objects.filter(is_active=True).select_related('category').prefetch_related('reviews__user', 'variants', 'images')

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['variants'] = self.object.variants.filter(is_active=True).order_by('size', 'color')
        context['average_rating'] = self.object.reviews.aggregate(value=Avg('rating'))['value']
        context['can_review'] = self.request.user.is_authenticated and Order.objects.filter(
            user=self.request.user,
            ordered=True,
            status='delivered',
            items__item=self.object,
        ).exists() and not Review.objects.filter(user=self.request.user, item=self.object).exists()
        context['reviews'] = self.object.reviews.select_related('user').order_by('-created_at')
        rating = self.request.GET.get('rating')
        if rating and rating.isdigit() and 1 <= int(rating) <= 5:
            context['reviews'] = context['reviews'].filter(rating=int(rating))
        return context


# class CategoryView(DetailView):
#     model = Category
#     template_name = "category.html"

class CategoryView(ListView):
    model = Item
    template_name = "category.html"
    paginate_by = 6

    def get_queryset(self):
        category = get_object_or_404(Category, slug=self.kwargs['slug'], is_active=True)
        qs = Item.objects.filter(category=category, is_active=True).annotate(
            effective_price=Coalesce('discount_price', 'price')
        )
        query = self.request.GET.get('q', '').strip()
        if query:
            qs = qs.filter(
                Q(title__icontains=query)
                | Q(description_short__icontains=query)
                | Q(description_long__icontains=query)
            )
        min_price = _clean_price_filter(self.request.GET.get('min_price'))
        max_price = _clean_price_filter(self.request.GET.get('max_price'))
        if min_price is not None:
            qs = qs.filter(effective_price__gte=min_price)
        if max_price is not None:
            qs = qs.filter(effective_price__lte=max_price)
        size = self.request.GET.get('size', '').strip()
        color = self.request.GET.get('color', '').strip()
        in_stock = self.request.GET.get('in_stock') == '1'
        variant_match = ItemVariant.objects.filter(item_id=OuterRef('pk'), is_active=True)
        if size:
            variant_match = variant_match.filter(size=size)
        if color:
            variant_match = variant_match.filter(color=color)
        if size or color:
            qs = qs.annotate(_matching_variant=Exists(variant_match.filter(stock_quantity__gt=0))).filter(_matching_variant=True)
        elif in_stock:
            qs = qs.annotate(
                _has_stock=Exists(ItemVariant.objects.filter(item_id=OuterRef('pk'), is_active=True, stock_quantity__gt=0)),
                _has_variant=Exists(ItemVariant.objects.filter(item_id=OuterRef('pk'), is_active=True)),
            ).filter(Q(_has_stock=True) | Q(_has_variant=False, stock_quantity__gt=0))
        orderings = {
            'price_asc': ('effective_price', 'title'),
            'price_desc': ('-effective_price', 'title'),
            'name': ('title',),
            'newest': ('-id',),
        }
        sort = self.request.GET.get('sort', 'newest')
        return qs.select_related('category').prefetch_related('variants').order_by(*orderings.get(sort, orderings['newest']))

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        category = get_object_or_404(Category, slug=self.kwargs['slug'], is_active=True)
        context['category_title'] = category
        context['category_description'] = category.description
        context['category_image'] = category.image
        context['active_filters'] = self.request.GET
        context['available_sizes'] = ItemVariant.objects.filter(item__category__slug=self.kwargs['slug'], is_active=True).values_list('size', flat=True).distinct().order_by('size')
        context['available_colors'] = ItemVariant.objects.filter(item__category__slug=self.kwargs['slug'], is_active=True).values_list('color', flat=True).distinct().order_by('color')
        return context


@method_decorator(login_required, name='dispatch')
class CheckoutView(View):
    def get(self, *args, **kwargs):
        try:
            order = Order.objects.get(user=self.request.user, ordered=False)
            if not order.items.exists():
                messages.info(self.request, "Your shopping bag is empty.")
                return redirect("core:order-summary")
            profile = UserProfile.objects.filter(user=self.request.user).first()
            full_name = self.request.user.get_full_name().strip() or self.request.user.username
            form = CheckoutForm(initial={
                'recipient_name': full_name,
                'phone_number': profile.phone if profile else '',
                'street_address': profile.address if profile else '',
            })
            context = {
                'form': form,
                'order': order,
                'couponform': CouponForm(),  # ✅ Thêm dòng này
                'DISPLAY_COUPON_FORM': True  # ✅ Dòng điều kiện để hiển thị form
            }
            return render(self.request, "checkout.html", context)
        except ObjectDoesNotExist:
            messages.info(self.request, "You do not have an active order")
            return redirect("core:order-summary")

    def post(self, *args, **kwargs):
        form = CheckoutForm(self.request.POST)
        try:
            with transaction.atomic():
                order = Order.objects.select_for_update().get(user=self.request.user, ordered=False)
                order_items = list(
                    order.items.select_related('item', 'variant').select_for_update(of=('self',))
                )

                if not order_items:
                    messages.info(self.request, "Your shopping bag is empty.")
                    return redirect("core:order-summary")

                if form.is_valid():
                    if self.request.POST.get('payment_option') != 'Cash on Delivery':
                        form.add_error(None, "Please choose Cash on Delivery to continue.")
                    else:
                        coupon = None
                        if order.coupon_id:
                            coupon = Coupon.objects.select_for_update().get(pk=order.coupon_id)
                            if not coupon.is_active or (coupon.expires_at and coupon.expires_at <= timezone.now()):
                                form.add_error(None, 'The discount code has expired or is no longer active.')
                            elif coupon.max_uses is not None and coupon.use_count >= coupon.max_uses:
                                form.add_error(None, 'The discount code has reached its usage limit.')
                            elif sum(line.get_final_price() for line in order_items) < coupon.minimum_order_amount:
                                form.add_error(None, f'This code requires a minimum order of ${coupon.minimum_order_amount:.2f}.')

                        for order_item in order_items:
                            item = Item.objects.select_for_update().get(pk=order_item.item_id)
                            stock = item.stock_quantity
                            if order_item.variant_id:
                                variant = ItemVariant.objects.select_for_update().get(pk=order_item.variant_id)
                                stock = variant.stock_quantity if variant.is_active and variant.item_id == item.pk else 0
                            if order_item.quantity < 1:
                                form.add_error(None, f"{item.title} has an invalid quantity in your bag.")
                            elif order_item.quantity > 99:
                                form.add_error(None, f"The maximum quantity per product is 99 ({item.title}).")
                            elif not item.is_active:
                                form.add_error(None, f"{item.title} is no longer available.")
                            elif order_item.user_id != self.request.user.pk:
                                form.add_error(None, f"The shopping bag contains an invalid line for {item.title}.")
                            elif order_item.variant_id and order_item.variant.item_id != item.pk:
                                form.add_error(None, f"The selected option does not belong to {item.title}.")
                            elif order_item.quantity > stock:
                                form.add_error(None, f"Only {stock} of {item.title} ({order_item.variant or 'standard'}) remain in stock.")

                        if not form.errors:
                            for order_item in order_items:
                                item = Item.objects.select_for_update().get(pk=order_item.item_id)
                                if order_item.variant_id:
                                    variant = ItemVariant.objects.select_for_update().get(pk=order_item.variant_id)
                                    variant.stock_quantity -= order_item.quantity
                                    variant.save(update_fields=['stock_quantity'])
                                else:
                                    item.stock_quantity -= order_item.quantity
                                    item.save(update_fields=['stock_quantity'])
                                StockMovement.objects.create(
                                    item=item,
                                    variant=order_item.variant,
                                    order=order,
                                    quantity_change=-order_item.quantity,
                                    reason='order',
                                    note='Stock reserved for customer order.',
                                    created_by=self.request.user,
                                )
                                order_item.unit_price = item.discount_price or item.price
                                order_item.ordered = True
                                order_item.save(update_fields=['unit_price', 'ordered'])

                            # Keep an order-time address snapshot on the order record.
                            billing_address = BillingAddress.objects.create(
                                user=self.request.user,
                                recipient_name=form.cleaned_data['recipient_name'],
                                phone_number=form.cleaned_data['phone_number'],
                                street_address=form.cleaned_data['street_address'],
                                default=False,
                            )
                            order.billing_address = billing_address
                            order.shipping_address = billing_address
                            order.ordered = True
                            order.status = 'pending'
                            order.payment_method = 'cod'
                            order.payment_status = 'pending'
                            order.payment = Payment.objects.create(
                                user=self.request.user,
                                amount=order.get_total(),
                                method='cod',
                                status='pending',
                            )
                            order.stock_deducted = True
                            order.ordered_date = timezone.now()
                            order.ref_code = create_ref_code()
                            order.save()
                            if coupon:
                                Coupon.objects.filter(pk=coupon.pk).update(use_count=F('use_count') + 1)
                            OrderStatusHistory.objects.create(
                                order=order,
                                status='pending',
                                note='Order placed. Waiting for shop confirmation.',
                                updated_by=self.request.user,
                            )
                            transaction.on_commit(lambda: send_order_status_email(
                                order.pk,
                                'pending',
                                'We have received your cash-on-delivery order.',
                            ))

                            messages.success(self.request, "Your order has been placed successfully!")
                            return redirect('core:order-success-detail', ref_code=order.ref_code)

            context = {
                'form': form,
                'order': order,
                'couponform': CouponForm(),
                'DISPLAY_COUPON_FORM': True,
            }
            return render(self.request, "checkout.html", context)

        except ObjectDoesNotExist:
            messages.warning(self.request, "You do not have an active order!")
            return redirect("core:checkout")



def order_success_view(request):
    if not request.user.is_authenticated:
        return redirect('account_login')
    order = Order.objects.filter(user=request.user, ordered=True).order_by('-ordered_date').first()
    if not order:
        messages.info(request, 'No recent order was found for your account.')
        return redirect('core:shop')
    return redirect('core:order-success-detail', ref_code=order.ref_code)


@login_required
def order_success_detail_view(request, ref_code):
    order = get_object_or_404(
        Order.objects.select_related('shipping_address').prefetch_related('items__item'),
        user=request.user,
        ref_code=ref_code,
        ordered=True,
    )
    return render(request, 'order_success.html', {'order': order})


@login_required
def order_detail_view(request, ref_code):
    order = get_object_or_404(
        Order.objects.prefetch_related('items__item', 'status_history'),
        ref_code=ref_code,
        user=request.user,
        ordered=True,
    )
    if request.method == 'POST':
        action = request.POST.get('action')
        if action == 'accept_shipping_fee':
            with transaction.atomic():
                order = Order.objects.select_for_update().get(pk=order.pk, user=request.user)
                if order.status not in {'pending', 'confirmed', 'packed'}:
                    messages.error(request, 'The delivery amount can no longer be changed for this order.')
                elif not order.shipping_fee_confirmed:
                    messages.error(request, 'The shop has not confirmed the delivery fee yet.')
                elif order.shipping_fee_accepted:
                    messages.info(request, 'You have already accepted this delivery total.')
                else:
                    order.shipping_fee_accepted = True
                    order.save(update_fields=('shipping_fee_accepted',))
                    OrderStatusHistory.objects.create(
                        order=order,
                        status=order.status,
                        note=f'Customer accepted the delivery fee and total of ${order.get_total():.2f}.',
                        updated_by=request.user,
                    )
                    messages.success(request, 'Delivery total accepted. The shop can now dispatch your order.')
            return redirect('core:order-detail', ref_code=ref_code)
        transitions = {
            'cancel': ('cancelled', {'pending', 'confirmed'}, 'Cancelled by customer.'),
            'received': ('delivered', {'shipped'}, 'Customer confirmed receipt.'),
        }
        if action not in transitions:
            messages.error(request, 'That order action is not available.')
        else:
            new_status, allowed, note = transitions[action]
            if order.status not in allowed:
                messages.error(request, 'This action is not available for the current order status.')
            else:
                try:
                    transition_order_status(order, new_status, request.user, note)
                    messages.success(request, 'Your order has been updated.')
                except ValidationError as exc:
                    messages.error(request, str(exc))
        return redirect('core:order-detail', ref_code=ref_code)
    return render(request, 'order_detail.html', {'order': order})


@login_required
@require_POST
@transaction.atomic
def reorder_order(request, ref_code):
    previous = get_object_or_404(Order, user=request.user, ref_code=ref_code, ordered=True)
    lines = list(previous.items.select_related('item', 'variant'))
    get_user_model().objects.select_for_update().get(pk=request.user.pk)
    cart, _ = Order.objects.get_or_create(
        user=request.user,
        ordered=False,
        defaults={'ordered_date': timezone.now()},
    )
    existing = {(line.item_id, line.variant_id): line for line in cart.items.select_for_update().filter(ordered=False)}
    to_add = []
    for line in lines:
        item = Item.objects.select_for_update().filter(pk=line.item_id, is_active=True).first()
        variant = ItemVariant.objects.select_for_update().filter(pk=line.variant_id, is_active=True).first() if line.variant_id else None
        if not item or (line.variant_id and not variant):
            messages.warning(request, f'{line.item.title} is no longer available; nothing was added.')
            return redirect('core:order-detail', ref_code=ref_code)
        stock = variant.stock_quantity if variant else item.stock_quantity
        already = existing.get((item.pk, variant.pk if variant else None))
        if (already.quantity if already else 0) + line.quantity > stock:
            messages.warning(request, f'Not enough stock for {item.title}; nothing was added.')
            return redirect('core:order-detail', ref_code=ref_code)
        to_add.append((item, variant, line.quantity, already))
    for item, variant, qty, already in to_add:
        if already:
            already.quantity += qty
            already.save(update_fields=['quantity'])
        else:
            new_line = OrderItem.objects.create(user=request.user, item=item, variant=variant, quantity=qty)
            cart.items.add(new_line)
    messages.success(request, 'The items from your previous order were added to the shopping bag.')
    return redirect('core:order-summary')


# def home(request):
#     context = {
#         'items': Item.objects.all()
#     }
#     return render(request, "index.html", context)
#
#
# def products(request):
#     context = {
#         'items': Item.objects.all()
#     }
#     return render(request, "product-detail.html", context)
#
#
# def shop(request):
#     context = {
#         'items': Item.objects.all()
#     }
#     return render(request, "shop.html", context)


@require_POST
@transaction.atomic
def add_to_cart(request, slug):
    item = get_object_or_404(Item.objects.select_for_update(), slug=slug, is_active=True)
    if not request.user.is_authenticated:
        messages.info(request, 'Sign in to add this product to your bag.')
        return redirect(f"{reverse('account_login')}?{urlencode({'next': item.get_absolute_url()})}")
    get_user_model().objects.select_for_update().get(pk=request.user.pk)
    variants = list(ItemVariant.objects.select_for_update().filter(item=item, is_active=True))
    variant = None
    if variants:
        variant_id = request.POST.get('variant')
        variant = next((candidate for candidate in variants if str(candidate.pk) == str(variant_id)), None)
        if variant is None:
            messages.warning(request, 'Choose an available size and color first.')
            return redirect('core:product', slug=slug)
        available_stock = variant.stock_quantity
    else:
        available_stock = item.stock_quantity
    if not item.is_active or available_stock < 1:
        messages.warning(request, "This item is currently out of stock.")
        return redirect("core:product", slug=slug)
    try:
        quantity = int(request.POST.get('quantity', '1'))
    except (TypeError, ValueError):
        quantity = 0
    if quantity < 1 or quantity > 99:
        messages.warning(request, 'Choose a quantity between 1 and 99.')
        return redirect('core:product', slug=slug)
    order, _ = Order.objects.get_or_create(
        user=request.user,
        ordered=False,
        defaults={'ordered_date': timezone.now()},
    )
    order_item = order.items.filter(item=item, variant=variant, ordered=False).first()
    next_quantity = quantity + (order_item.quantity if order_item else 0)
    if next_quantity > available_stock:
        messages.warning(request, f'Only {available_stock} of this option are available.')
        return redirect('core:order-summary')
    if order_item:
        order_item.quantity = next_quantity
        order_item.save(update_fields=['quantity'])
    else:
        order_item = OrderItem.objects.create(user=request.user, item=item, variant=variant, quantity=quantity, ordered=False)
        order.items.add(order_item)
    messages.success(request, 'Added to your shopping bag.')
    return redirect("core:order-summary")


@login_required
@require_POST
@transaction.atomic
def remove_from_cart(request, slug):
    item = get_object_or_404(Item, slug=slug)
    order = Order.objects.select_for_update().filter(user=request.user, ordered=False).first()
    if order:
        # check if the order item is in the order
        variant_id = request.POST.get('variant') or None
        order_item = order.items.select_for_update().filter(
            item__slug=item.slug, variant_id=variant_id, user=request.user, ordered=False
        ).first()
        if order_item:
            order.items.remove(order_item)
            messages.info(request, "Item was removed from your cart.")
            return redirect("core:order-summary")
        else:
            # add a message saying the user dosent have an order
            messages.info(request, "Item was not in your cart.")
            return redirect("core:product", slug=slug)
    else:
        # add a message saying the user dosent have an order
        messages.info(request, "You don't have an active order.")
        return redirect("core:product", slug=slug)
    return redirect("core:product", slug=slug)


@login_required
@require_POST
@transaction.atomic
def remove_single_item_from_cart(request, slug):
    item = get_object_or_404(Item, slug=slug)
    order = Order.objects.select_for_update().filter(user=request.user, ordered=False).first()
    if order:
        # check if the order item is in the order
        variant_id = request.POST.get('variant') or None
        order_item = order.items.select_for_update().filter(
            item__slug=item.slug, variant_id=variant_id, user=request.user, ordered=False
        ).first()
        if order_item:
            if order_item.quantity > 1:
                order_item.quantity -= 1
                order_item.save()
            else:
                order.items.remove(order_item)
            messages.info(request, "This item quality was updated.")
            return redirect("core:order-summary")
        else:
            # add a message saying the user dosent have an order
            messages.info(request, "Item was not in your cart.")
            return redirect("core:product", slug=slug)
    else:
        # add a message saying the user dosent have an order
        messages.info(request, "You don't have an active order.")
        return redirect("core:product", slug=slug)
    return redirect("core:product", slug=slug)


def get_coupon(request, code):
    try:
        coupon = Coupon.objects.get(code=code)
        return coupon
    except ObjectDoesNotExist:
        messages.info(request, "This coupon does not exist")
        return redirect("core:checkout")


@method_decorator(login_required, name='dispatch')
class AddCouponView(View):
    def post(self, *args, **kwargs):
        form = CouponForm(self.request.POST or None)
        if form.is_valid():
            try:
                code = form.cleaned_data.get('code')
                with transaction.atomic():
                    order = Order.objects.select_for_update().get(user=self.request.user, ordered=False)
                    coupon = Coupon.objects.select_for_update().get(code__iexact=code)
                    if not coupon.is_active or (coupon.expires_at and coupon.expires_at <= timezone.now()):
                        messages.warning(self.request, 'This discount code has expired or is inactive.')
                        return redirect('core:checkout')
                    if coupon.max_uses is not None and coupon.use_count >= coupon.max_uses:
                        messages.warning(self.request, 'This discount code has reached its usage limit.')
                        return redirect('core:checkout')
                    if sum(line.get_final_price() for line in order.items.all()) < coupon.minimum_order_amount:
                        messages.warning(self.request, f'This code requires a minimum order of ${coupon.minimum_order_amount:.2f}.')
                        return redirect('core:checkout')
                    order.coupon = coupon
                    order.save()
                    messages.success(self.request, f"Successfully applied coupon: {code}")
                    return redirect("core:checkout")
            except ObjectDoesNotExist:
                messages.info(self.request, "Coupon or active shopping bag was not found.")
                return redirect("core:checkout")
        
        messages.warning(self.request, "Invalid coupon code")
        return redirect("core:checkout")



class RequestRefundView(View):
    def get(self, *args, **kwargs):
        form = RefundForm()
        context = {
            'form': form
        }
        return render(self.request, "request_refund.html", context)

    def post(self, *args, **kwargs):
        form = RefundForm(self.request.POST)
        if form.is_valid():
            ref_code = form.cleaned_data.get('ref_code')
            message = form.cleaned_data.get('message')
            email = form.cleaned_data.get('email')
            order = None
            with transaction.atomic():
                order = Order.objects.select_for_update().filter(
                    ref_code=ref_code,
                    user__email__iexact=email,
                    ordered=True,
                ).first()
                if not order:
                    form.add_error(None, 'We could not find an order matching that reference and email.')
                elif order.status != 'delivered':
                    form.add_error(None, 'A refund can be requested after the order has been delivered.')
                else:
                    refund = Refund.objects.select_for_update().filter(order=order).first()
                    if refund and not refund.rejected:
                        form.add_error(None, 'A return request is already being reviewed for this order.')
                    else:
                        if refund:
                            refund.reason = message
                            refund.email = email
                            refund.accepted = False
                            refund.items_received = False
                            refund.restocked = False
                            refund.rejected = False
                            refund.rejection_reason = ''
                            refund.refund_method = ''
                            refund.refund_reference = ''
                            refund.refund_amount = None
                            refund.refunded_by = None
                            refund.refunded_at = None
                            refund.processed_by = None
                            refund.processed_at = None
                            refund.save()
                        else:
                            Refund.objects.create(order=order, reason=message, email=email)
                        transition_order_status(order, 'refund_requested', None, 'Customer requested a return and refund.')
                        messages.info(self.request, 'Your return request was received.')
                        return redirect('core:order-detail', ref_code=ref_code) if self.request.user.is_authenticated and self.request.user == order.user else redirect('core:request-refund')

        return render(self.request, 'request_refund.html', {'form': form})

@login_required
def profile_view(request):
    user_profile, created = UserProfile.objects.get_or_create(user=request.user)
    order_queryset = (
        Order.objects.filter(user=request.user, ordered=True)
        .select_related('shipping_address')
        .prefetch_related('items__item')
        .order_by('-ordered_date')
    )
    order_count = order_queryset.count()
    orders = Paginator(order_queryset, 10).get_page(request.GET.get('orders_page'))
    form = ProfileForm(
        request.POST or None,
        request.FILES or None,
        instance=user_profile,
        initial={
            'first_name': request.user.first_name,
            'last_name': request.user.last_name,
            'email': request.user.email,
        },
    )
    if request.method == "POST" and form.is_valid():
        request.user.first_name = form.cleaned_data['first_name']
        request.user.last_name = form.cleaned_data['last_name']
        request.user.email = form.cleaned_data['email']
        request.user.save(update_fields=['first_name', 'last_name', 'email'])
        form.save()
        messages.success(request, "Your profile has been updated.")
        return redirect("core:profile")
    context = {
        'profile': user_profile,
        'orders': orders,
        'order_count': order_count,
        'form': form,
    }
    return render(request, "profile.html", context)

@login_required
def wishlist_view(request):
    wishlist, created = Wishlist.objects.get_or_create(user=request.user)
    context = {
        'wishlist': wishlist
    }
    return render(request, "wishlist.html", context)

@require_POST
def add_to_wishlist(request, slug):
    item = get_object_or_404(Item, slug=slug)
    if not request.user.is_authenticated:
        return redirect(f"{reverse('account_login')}?{urlencode({'next': item.get_absolute_url()})}")
    wishlist, created = Wishlist.objects.get_or_create(user=request.user)
    if item in wishlist.items.all():
        messages.info(request, "This item is already in your wishlist.")
    else:
        wishlist.items.add(item)
        messages.success(request, "Item added to your wishlist.")
    return redirect("core:product", slug=slug)

@login_required
@require_POST
def remove_from_wishlist(request, slug):
    item = get_object_or_404(Item, slug=slug)
    wishlist = get_object_or_404(Wishlist, user=request.user)
    if item in wishlist.items.all():
        wishlist.items.remove(item)
        messages.success(request, "Item removed from your wishlist.")
    return redirect("core:wishlist")

@login_required
@require_POST
def add_review(request, slug):
    if request.method == "POST":
        item = get_object_or_404(Item, slug=slug)
        try:
            rating = int(request.POST.get('rating', ''))
        except (TypeError, ValueError):
            rating = 0
        comment = (request.POST.get('comment') or '').strip()
        
        # Check if user already ordered this item (optional business logic, but good practice)
        has_ordered = Order.objects.filter(
            user=request.user,
            ordered=True,
            status='delivered',
            items__item=item,
        ).exists()
        if not has_ordered:
            messages.warning(request, "You can review this product after your delivered order arrives.")
            return redirect("core:product", slug=slug)

        if rating not in range(1, 6) or not comment:
            messages.warning(request, 'Choose a rating from 1 to 5 and write a short review.')
            return redirect('core:product', slug=slug)

        if Review.objects.filter(user=request.user, item=item).exists():
            messages.info(request, 'You have already reviewed this product.')
            return redirect('core:product', slug=slug)

        photo = request.FILES.get('photo')
        if photo and (photo.size > 5 * 1024 * 1024 or photo.content_type not in {'image/jpeg', 'image/png', 'image/webp'}):
            messages.warning(request, 'Review photos must be JPG, PNG or WebP and no larger than 5 MB.')
            return redirect('core:product', slug=slug)
        if photo:
            from django.core.files.images import get_image_dimensions
            try:
                if not all(get_image_dimensions(photo)):
                    raise ValueError('Invalid image dimensions')
            except Exception:
                messages.warning(request, 'That review photo could not be read as a valid image.')
                return redirect('core:product', slug=slug)
        Review.objects.create(
            user=request.user,
            item=item,
            rating=rating,
            comment=comment,
            photo=photo,
        )
        messages.success(request, "Your review has been submitted!")
    return redirect("core:product", slug=slug)
