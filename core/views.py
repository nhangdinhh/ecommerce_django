from django.conf import settings
from django.contrib import messages
from django.core.exceptions import ObjectDoesNotExist
from django.contrib.auth.decorators import login_required
from django.contrib.auth.mixins import LoginRequiredMixin
from django.shortcuts import render, get_object_or_404
from django.views.generic import ListView, DetailView, View
from django.shortcuts import redirect
from django.utils import timezone
from .forms import CheckoutForm, CouponForm, RefundForm
from .models import Item, OrderItem, Order, BillingAddress, Payment, Coupon, Refund, Category, UserProfile, Wishlist, Review
from django.http import HttpResponseRedirect
from django.shortcuts import render
# Create your views here.
import random
import string
import stripe
stripe.api_key = settings.STRIPE_SECRET_KEY


def create_ref_code():
    return ''.join(random.choices(string.ascii_lowercase + string.digits, k=20))


class PaymentView(View):
    def get(self, *args, **kwargs):
        # order
        order = Order.objects.get(user=self.request.user, ordered=False)
        if order.billing_address:
            context = {
                'order': order,
                'DISPLAY_COUPON_FORM': False
            }
            return render(self.request, "payment.html", context)
        else:
            messages.warning(
                self.request, "u have not added a billing address")
            return redirect("core:checkout")

    def post(self, *args, **kwargs):
        order = Order.objects.get(user=self.request.user, ordered=False)
        token = self.request.POST.get('stripeToken')
        amount = int(order.get_total() * 100)
        try:
            charge = stripe.Charge.create(
                amount=amount,  # cents
                currency="usd",
                source=token
            )
            # create the payment
            payment = Payment()
            payment.stripe_charge_id = charge['id']
            payment.user = self.request.user
            payment.amount = order.get_total()
            payment.save()

            # assign the payment to the order
            order.ordered = True
            order.payment = payment
            # TODO : assign ref code
            order.ref_code = create_ref_code()
            order.save()

            messages.success(self.request, "Order was successful")
            return redirect("/")

        except stripe.error.CardError as e:
            # Since it's a decline, stripe.error.CardError will be caught
            body = e.json_body
            err = body.get('error', {})
            messages.error(self.request, f"{err.get('message')}")
            return redirect("/")

        except stripe.error.RateLimitError as e:
            # Too many requests made to the API too quickly
            messages.error(self.request, "RateLimitError")
            return redirect("/")

        except stripe.error.InvalidRequestError as e:
            # Invalid parameters were supplied to Stripe's API
            messages.error(self.request, "Invalid parameters")
            return redirect("/")

        except stripe.error.AuthenticationError as e:
            # Authentication with Stripe's API failed
            # (maybe you changed API keys recently)
            messages.error(self.request, "Not Authentication")
            return redirect("/")

        except stripe.error.APIConnectionError as e:
            # Network communication with Stripe failed
            messages.error(self.request, "Network Error")
            return redirect("/")

        except stripe.error.StripeError as e:
            # Display a very generic error to the user, and maybe send
            # yourself an email
            messages.error(self.request, "Something went wrong")
            return redirect("/")

        except Exception as e:
            # send an email to ourselves
            messages.error(self.request, "Serious Error occured")
            return redirect("/")


class HomeView(ListView):
    template_name = "index.html"
    context_object_name = 'items'

    def get_queryset(self):
        qs = Item.objects.filter(is_active=True)
        q = self.request.GET.get('q')
        if q:
            qs = qs.filter(title__icontains=q)
        return qs


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
        qs = super().get_queryset()
        q = self.request.GET.get('q')
        if q:
            qs = qs.filter(title__icontains=q)
            
        min_price = self.request.GET.get('min_price')
        max_price = self.request.GET.get('max_price')
        try:
            if min_price:
                qs = qs.filter(price__gte=float(min_price))
            if max_price:
                qs = qs.filter(price__lte=float(max_price))
        except ValueError:
            pass
            
        return qs


class ItemDetailView(DetailView):
    model = Item
    template_name = "product-detail.html"


# class CategoryView(DetailView):
#     model = Category
#     template_name = "category.html"

class CategoryView(ListView):
    model = Item
    template_name = "category.html"
    paginate_by = 6

    def get_queryset(self):
        category = Category.objects.get(slug=self.kwargs['slug'])
        qs = Item.objects.filter(category=category, is_active=True)
        
        min_price = self.request.GET.get('min_price')
        max_price = self.request.GET.get('max_price')
        try:
            if min_price:
                qs = qs.filter(price__gte=float(min_price))
            if max_price:
                qs = qs.filter(price__lte=float(max_price))
        except ValueError:
            pass
        return qs

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        category = Category.objects.get(slug=self.kwargs['slug'])
        context['category_title'] = category
        context['category_description'] = category.description
        context['category_image'] = category.image
        return context


# views.py

from django.utils import timezone
import random, string

def create_ref_code():
    return ''.join(random.choices(string.ascii_lowercase + string.digits, k=20))

class CheckoutView(View):
    def get(self, *args, **kwargs):
        try:
            order = Order.objects.get(user=self.request.user, ordered=False)
            form = CheckoutForm()
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
        form = CheckoutForm(self.request.POST or None)
        try:
            order = Order.objects.get(user=self.request.user, ordered=False)

            if form.is_valid():
                street_address = form.cleaned_data.get('street_address')
                note = self.request.POST.get('note', '')
                payment_option = self.request.POST.get('payment_option')  # COD

                # Save BillingAddress
                billing_address = BillingAddress.objects.create(
                    user=self.request.user,
                    street_address=street_address,
                    default=False
                )
                order.billing_address = billing_address

                # ✅ Save the order details
                order.ordered = True
                order.ordered_date = timezone.now()
                order.ref_code = create_ref_code()
                order.save()

                messages.success(self.request, "Your order has been placed successfully!")
                return redirect('core:order-success')

            messages.warning(self.request, "Form is invalid")
            return redirect("core:checkout")

        except ObjectDoesNotExist:
            messages.warning(self.request, "You do not have an active order!")
            return redirect("core:checkout")



def order_success_view(request):
    return render(request, 'order_success.html')
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


@login_required
def add_to_cart(request, slug):
    item = get_object_or_404(Item, slug=slug)
    order_item, created = OrderItem.objects.get_or_create(
        item=item,
        user=request.user,
        ordered=False
    )
    order_qs = Order.objects.filter(user=request.user, ordered=False)
    if order_qs.exists():
        order = order_qs[0]
        if order.items.filter(item__slug=item.slug).exists():
            order_item.quantity += 1
            order_item.save()
            messages.info(request, "Item qty was updated.")
            return redirect("core:order-summary")
        else:
            order.items.add(order_item)
            messages.info(request, "Item was added to your cart.")
            return redirect("core:order-summary")
    else:
        ordered_date = timezone.now()
        order = Order.objects.create(
            user=request.user, ordered_date=ordered_date)
        order.items.add(order_item)
        messages.info(request, "Item was added to your cart.")
    return redirect("core:order-summary")


@login_required
def remove_from_cart(request, slug):
    item = get_object_or_404(Item, slug=slug)
    order_qs = Order.objects.filter(
        user=request.user,
        ordered=False)
    if order_qs.exists():
        order = order_qs[0]
        # check if the order item is in the order
        if order.items.filter(item__slug=item.slug).exists():
            order_item = OrderItem.objects.filter(
                item=item,
                user=request.user,
                ordered=False
            )[0]
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
def remove_single_item_from_cart(request, slug):
    item = get_object_or_404(Item, slug=slug)
    order_qs = Order.objects.filter(
        user=request.user,
        ordered=False)
    if order_qs.exists():
        order = order_qs[0]
        # check if the order item is in the order
        if order.items.filter(item__slug=item.slug).exists():
            order_item = OrderItem.objects.filter(
                item=item,
                user=request.user,
                ordered=False
            )[0]
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


class AddCouponView(View):
    def post(self, *args, **kwargs):
        form = CouponForm(self.request.POST or None)
        if form.is_valid():
            try:
                code = form.cleaned_data.get('code')
                order = Order.objects.get(user=self.request.user, ordered=False)
                try:
                    coupon = Coupon.objects.get(code=code)
                    order.coupon = coupon
                    order.save()
                    messages.success(self.request, f"Successfully applied coupon: {code}")
                    return redirect("core:checkout")
                except ObjectDoesNotExist:
                    messages.info(self.request, "This coupon does not exist")
                    return redirect("core:checkout")
            except ObjectDoesNotExist:
                messages.info(self.request, "You do not have an active order")
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
            # edit the order
            try:
                order = Order.objects.get(ref_code=ref_code)
                order.refund_requested = True
                order.save()

                # store the refund
                refund = Refund()
                refund.order = order
                refund.reason = message
                refund.email = email
                refund.save()

                messages.info(self.request, "Your request was received")
                return redirect("core:request-refund")

            except ObjectDoesNotExist:
                messages.info(self.request, "This order does not exist")
                return redirect("core:request-refund")

@login_required
def profile_view(request):
    user_profile, created = UserProfile.objects.get_or_create(user=request.user)
    orders = Order.objects.filter(user=request.user, ordered=True).order_by('-ordered_date')
    context = {
        'profile': user_profile,
        'orders': orders
    }
    return render(request, "profile.html", context)

@login_required
def wishlist_view(request):
    wishlist, created = Wishlist.objects.get_or_create(user=request.user)
    context = {
        'wishlist': wishlist
    }
    return render(request, "wishlist.html", context)

@login_required
def add_to_wishlist(request, slug):
    item = get_object_or_404(Item, slug=slug)
    wishlist, created = Wishlist.objects.get_or_create(user=request.user)
    if item in wishlist.items.all():
        messages.info(request, "This item is already in your wishlist.")
    else:
        wishlist.items.add(item)
        messages.success(request, "Item added to your wishlist.")
    return redirect("core:product", slug=slug)

@login_required
def remove_from_wishlist(request, slug):
    item = get_object_or_404(Item, slug=slug)
    wishlist = get_object_or_404(Wishlist, user=request.user)
    if item in wishlist.items.all():
        wishlist.items.remove(item)
        messages.success(request, "Item removed from your wishlist.")
    return redirect("core:wishlist")

@login_required
def add_review(request, slug):
    if request.method == "POST":
        item = get_object_or_404(Item, slug=slug)
        rating = request.POST.get('rating')
        comment = request.POST.get('comment')
        
        # Check if user already ordered this item (optional business logic, but good practice)
        has_ordered = OrderItem.objects.filter(user=request.user, item=item, ordered=True).exists()
        if not has_ordered:
            messages.warning(request, "You can only review products you have purchased.")
            return redirect("core:product", slug=slug)

        Review.objects.create(
            user=request.user,
            item=item,
            rating=rating,
            comment=comment
        )
        messages.success(request, "Your review has been submitted!")
    return redirect("core:product", slug=slug)
