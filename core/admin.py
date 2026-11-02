from django import forms
from django.contrib import admin, messages
from django.db import transaction
from django.db.models import Exists, F, OuterRef, Q, Sum, Count
from django.db.models.functions import TruncDate
from django.urls import path
from django.shortcuts import render
from django.utils import timezone
from django.utils.html import format_html
from datetime import timedelta
from django.core.exceptions import ValidationError

from .models import BillingAddress, Category, Coupon, Item, ItemImage, ItemVariant, Order, OrderItem, OrderStatusHistory, Payment, Refund, Slide, StockMovement, Supplier, StockReceipt, Review, PriceHistory
from .order_workflow import ALLOWED_TRANSITIONS, transition_order_status
from .notifications import send_order_status_email, send_shipping_quote_email


ADMIN_FIELD_LABELS = {
    'order': {'user': 'Khách hàng', 'ref_code': 'Mã đơn hàng', 'items': 'Sản phẩm', 'start_date': 'Ngày tạo giỏ', 'ordered_date': 'Ngày đặt hàng', 'ordered': 'Đã đặt hàng', 'status': 'Trạng thái đơn', 'payment_method': 'Phương thức thanh toán', 'payment_status': 'Trạng thái thanh toán', 'shipping_fee': 'Phí giao hàng', 'shipping_fee_accepted': 'Customer accepted total', 'shipping_fee_confirmed': 'Đã xác nhận phí giao hàng', 'shipping_carrier': 'Đơn vị vận chuyển', 'tracking_number': 'Mã vận đơn', 'shipped_at': 'Ngày gửi hàng', 'delivered_at': 'Ngày giao hàng', 'stock_deducted': 'Đã trừ tồn kho', 'shipping_address': 'Địa chỉ giao hàng', 'billing_address': 'Địa chỉ thanh toán', 'payment': 'Giao dịch thanh toán', 'coupon': 'Mã giảm giá'},
    'item': {'title': 'Tên sản phẩm', 'price': 'Giá bán', 'discount_price': 'Giá khuyến mãi', 'category': 'Danh mục', 'label': 'Nhãn sản phẩm', 'slug': 'Đường dẫn', 'stock_no': 'Mã kho', 'stock_quantity': 'Tồn kho', 'reorder_level': 'Ngưỡng cảnh báo tồn kho', 'description_short': 'Mô tả ngắn', 'description_long': 'Mô tả chi tiết', 'image': 'Ảnh chính', 'is_active': 'Đang kinh doanh'},
    'itemvariant': {'item': 'Sản phẩm', 'size': 'Kích cỡ', 'color': 'Màu sắc', 'sku': 'Mã SKU', 'stock_quantity': 'Tồn kho', 'reorder_level': 'Ngưỡng nhập lại', 'is_active': 'Đang bán'},
    'itemimage': {'item': 'Sản phẩm', 'image': 'Ảnh', 'alt_text': 'Văn bản thay thế', 'sort_order': 'Thứ tự hiển thị'},
    'pricehistory': {'item': 'Sản phẩm', 'old_price': 'Giá cũ', 'new_price': 'Giá mới', 'old_discount_price': 'Giá khuyến mãi cũ', 'new_discount_price': 'Giá khuyến mãi mới', 'changed_by': 'Người cập nhật', 'changed_at': 'Thời điểm cập nhật', 'note': 'Ghi chú'},
    'category': {'title': 'Tên danh mục', 'slug': 'Đường dẫn', 'description': 'Mô tả', 'image': 'Ảnh danh mục', 'is_active': 'Đang hiển thị'},
    'slide': {'caption1': 'Tiêu đề nhỏ', 'caption2': 'Tiêu đề chính', 'link': 'Liên kết', 'image': 'Ảnh banner', 'is_active': 'Đang hiển thị'},
    'orderstatushistory': {'order': 'Đơn hàng', 'status': 'Trạng thái', 'note': 'Ghi chú cập nhật', 'updated_by': 'Người cập nhật', 'created_at': 'Thời điểm'},
    'payment': {'stripe_charge_id': 'Mã giao dịch', 'user': 'Khách hàng', 'amount': 'Số tiền', 'method': 'Phương thức', 'status': 'Trạng thái', 'timestamp': 'Thời điểm'},
    'coupon': {'code': 'Mã giảm giá', 'amount': 'Giá trị giảm', 'minimum_order_amount': 'Giá trị đơn tối thiểu', 'is_active': 'Đang hoạt động', 'expires_at': 'Hết hạn lúc', 'max_uses': 'Số lượt tối đa', 'use_count': 'Đã sử dụng'},
    'refund': {'order': 'Order', 'reason': 'Return reason', 'accepted': 'Return approved', 'email': 'Customer email', 'items_received': 'Returned parcel received', 'restocked': 'Restocked', 'processed_by': 'Processed by', 'processed_at': 'Processed at', 'rejected': 'Rejected', 'rejection_reason': 'Rejection reason', 'refund_method': 'Refund method', 'refund_reference': 'Refund reference', 'refund_amount': 'Refund amount', 'refunded_by': 'Refunded by', 'refunded_at': 'Refunded at'},
    'stockreceipt': {'supplier': 'Nhà cung cấp', 'item': 'Sản phẩm', 'variant': 'Biến thể', 'reference': 'Mã phiếu nhập', 'quantity': 'Số lượng nhập', 'unit_cost': 'Giá nhập mỗi sản phẩm', 'received_at': 'Ngày nhập kho', 'received_by': 'Người nhận hàng', 'note': 'Ghi chú'},
    'stockmovement': {'item': 'Sản phẩm', 'variant': 'Biến thể', 'order': 'Đơn hàng', 'quantity_change': 'Thay đổi số lượng', 'reason': 'Lý do', 'note': 'Ghi chú', 'created_by': 'Người thực hiện', 'created_at': 'Thời điểm'},
    'supplier': {'name': 'Tên nhà cung cấp', 'contact_name': 'Người liên hệ', 'email': 'Email', 'phone': 'Số điện thoại', 'notes': 'Ghi chú', 'is_active': 'Đang hợp tác'},
    'review': {'item': 'Sản phẩm', 'user': 'Khách hàng', 'rating': 'Số sao', 'comment': 'Nội dung đánh giá', 'photo': 'Ảnh đánh giá', 'created_at': 'Ngày đánh giá'},
}

ADMIN_CHOICE_LABELS = {
    ('order', 'status'): {'pending': 'Chờ xác nhận', 'confirmed': 'Đã xác nhận', 'packed': 'Đã đóng gói', 'shipped': 'Đang giao', 'delivery_failed': 'Giao thất bại', 'returning': 'Đang hoàn về shop', 'returned': 'Đã hoàn về shop', 'delivered': 'Đã giao', 'cancelled': 'Đã hủy', 'refund_requested': 'Đang yêu cầu hoàn trả', 'refunded': 'Đã hoàn tiền'},
    ('order', 'payment_method'): {'cod': 'Thanh toán khi nhận hàng', 'card': 'Thẻ'},
    ('order', 'payment_status'): {'pending': 'Chờ thu tiền', 'paid': 'Đã thanh toán', 'refunded': 'Đã hoàn tiền', 'cancelled': 'Đã hủy'},
    ('payment', 'method'): {'cod': 'Thanh toán khi nhận hàng', 'card': 'Thẻ'},
    ('payment', 'status'): {'pending': 'Chờ thu tiền', 'paid': 'Đã thanh toán', 'refunded': 'Đã hoàn tiền', 'cancelled': 'Đã hủy'},
    ('stockmovement', 'reason'): {'order': 'Giữ hàng cho đơn', 'cancellation': 'Trả hàng sau khi hủy', 'adjustment': 'Điều chỉnh tồn kho', 'purchase': 'Nhập từ nhà cung cấp', 'refund_return': 'Nhập lại hàng hoàn', 'delivery_return': 'Hoàn về sau giao thất bại'},
    ('item', 'label'): {'S': 'Khuyến mãi', 'N': 'Hàng mới', 'P': 'Ưu đãi'},
}


class VietnameseAdminMixin:
    def formfield_for_dbfield(self, db_field, request, **kwargs):
        field = super().formfield_for_dbfield(db_field, request, **kwargs)
        if field is None:
            return field
        model_name = self.model._meta.model_name
        field.label = ADMIN_FIELD_LABELS.get(model_name, {}).get(db_field.name, field.label)
        translations = ADMIN_CHOICE_LABELS.get((model_name, db_field.name), {})
        if translations and hasattr(field, 'choices'):
            field.choices = [(value, translations.get(value, label)) for value, label in field.choices]
        return field


class OrderStatusHistoryInline(VietnameseAdminMixin, admin.TabularInline):
    model = OrderStatusHistory
    extra = 0
    can_delete = False
    readonly_fields = ('status', 'note', 'updated_by', 'created_at')

    def has_add_permission(self, request, obj=None):
        return False


class OrderAdminForm(forms.ModelForm):
    staff_note = forms.CharField(
        label='Ghi chú xử lý',
        required=False,
        max_length=255,
        help_text='Ghi chú sẽ được lưu vào lịch sử đơn hàng và gửi cho khách qua email.',
        widget=forms.TextInput(attrs={'placeholder': 'Ví dụ: Đơn hàng đã đóng gói, chờ bàn giao cho đơn vị vận chuyển'}),
    )

    class Meta:
        model = Order
        fields = '__all__'

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        status_field = self.fields.get('status')
        if status_field:
            current = self.instance.status if self.instance.pk else 'pending'
            allowed = {current, *ALLOWED_TRANSITIONS.get(current, set())}
            labels = ADMIN_CHOICE_LABELS['order', 'status']
            status_field.choices = [
                (value, labels.get(value, label))
                for value, label in Order._meta.get_field('status').choices
                if value in allowed
            ]

    def clean_status(self):
        new_status = self.cleaned_data['status']
        if self.instance.pk and new_status != self.instance.status:
            if new_status not in ALLOWED_TRANSITIONS.get(self.instance.status, set()):
                raise ValidationError(
                    'Không thể chuyển đơn hàng từ trạng thái hiện tại sang trạng thái đã chọn.'
                )
        return new_status

    def clean(self):
        cleaned_data = super().clean()
        status = cleaned_data.get('status')
        shipping_fee = cleaned_data.get('shipping_fee')
        shipping_fee_confirmed = cleaned_data.get('shipping_fee_confirmed')
        if shipping_fee is not None and shipping_fee < 0:
            self.add_error('shipping_fee', 'Phí giao hàng không được là số âm.')
        if shipping_fee and not shipping_fee_confirmed:
            self.add_error('shipping_fee_confirmed', 'Hãy xác nhận phí giao hàng trước khi lưu mức phí khác 0.')
        if (
            self.instance.pk
            and self.instance.status in {'shipped', 'delivery_failed', 'returning', 'returned', 'delivered', 'cancelled', 'refund_requested', 'refunded'}
            and (
                shipping_fee != self.instance.shipping_fee
                or shipping_fee_confirmed != self.instance.shipping_fee_confirmed
            )
        ):
            self.add_error('shipping_fee', 'Không thể đổi phí giao hàng sau khi đơn đã rời cửa hàng.')
        is_newly_shipped = status == 'shipped' and (
            not self.instance.pk or self.instance.status != 'shipped'
        )
        if is_newly_shipped:
            if not cleaned_data.get('shipping_carrier'):
                self.add_error('shipping_carrier', 'Nhập đơn vị vận chuyển trước khi chuyển đơn sang trạng thái đang giao.')
            if not cleaned_data.get('tracking_number'):
                self.add_error('tracking_number', 'Nhập mã vận đơn trước khi chuyển đơn sang trạng thái đang giao.')
            if not shipping_fee_confirmed:
                self.add_error('shipping_fee_confirmed', 'Xác nhận phí giao hàng (kể cả phí 0 đồng) trước khi gửi hàng.')
            if not getattr(self.instance, 'shipping_fee_accepted', False):
                self.add_error('status', 'Khách hàng cần xác nhận tổng tiền giao hàng trước khi chuyển đơn sang đang giao.')
        return cleaned_data


@admin.register(Order)
class OrderAdmin(VietnameseAdminMixin, admin.ModelAdmin):
    form = OrderAdminForm
    # Search related records on demand instead of rendering huge FK dropdowns.
    autocomplete_fields = ('user', 'shipping_address', 'billing_address', 'coupon')
    change_list_template = 'admin/core/order/change_list.html'
    list_display = ('order_reference', 'customer', 'status_text', 'payment_status_text', 'order_total', 'ordered_date_text', 'carrier_text', 'tracking_text')
    list_display_links = ('order_reference',)
    list_filter = ('status', 'payment_method', 'payment_status', 'ordered_date')
    search_fields = ('ref_code', 'user__username', 'user__email', 'tracking_number')
    date_hierarchy = 'ordered_date'
    ordering = ('-ordered_date', '-pk')
    actions = (
        'confirm_selected_orders', 'pack_selected_orders', 'mark_selected_shipped',
        'mark_delivery_failed', 'retry_failed_deliveries', 'mark_returning_to_shop',
        'mark_returned_to_shop', 'cancel_selected_orders',
    )
    readonly_fields = (
        'ref_code', 'start_date', 'ordered_date', 'shipped_at', 'delivered_at',
        'payment_method', 'payment_status', 'payment', 'being_delivered',
        'received', 'refund_requested', 'refund_granted', 'stock_deducted', 'shipping_fee_accepted',
        # Order lines are created by checkout. Rendering an editable M2M select
        # here loads every OrderItem in the database and becomes unusable at scale.
        'items',
    )
    inlines = (OrderStatusHistoryInline,)
    fieldsets = (
        ('Xử lý đơn hàng', {'fields': ('user', 'ref_code', 'items', 'ordered', 'status', 'staff_note', 'coupon')}),
        ('Thanh toán', {'fields': ('payment_method', 'payment_status', 'payment')}),
        ('Giao hàng', {'fields': ('shipping_address', 'billing_address', 'shipping_fee', 'shipping_fee_confirmed', 'shipping_fee_accepted', 'shipping_carrier', 'tracking_number', 'shipped_at', 'delivered_at')}),
        ('Thời gian', {'fields': ('start_date', 'ordered_date')}),
        ('Trường cũ', {'classes': ('collapse',), 'fields': ('being_delivered', 'received', 'refund_requested', 'refund_granted', 'stock_deducted')}),
    )

    def has_add_permission(self, request):
        # Orders must be created through checkout so stock and payment state
        # are initialized together.
        return False

    @admin.display(description='Mã đơn hàng', ordering='ref_code')
    def order_reference(self, obj):
        return obj.ref_code

    @admin.display(description='Khách hàng', ordering='user__username')
    def customer(self, obj):
        return obj.user.get_full_name() or obj.user.username

    @admin.display(description='Trạng thái đơn', ordering='status')
    def status_text(self, obj):
        label = ADMIN_CHOICE_LABELS['order', 'status'].get(obj.status, obj.get_status_display())
        palette = {
            'pending': ('#8a5a16', '#fff3d6'), 'confirmed': ('#345f91', '#eaf2fc'),
            'packed': ('#65509b', '#f0ebfb'), 'shipped': ('#216d68', '#e5f4f1'),
            'delivery_failed': ('#a33d2e', '#fff0ed'), 'returning': ('#8a5a16', '#fff3d6'),
            'returned': ('#65594b', '#efebe4'), 'delivered': ('#356b3f', '#eaf5e8'),
            'cancelled': ('#65594b', '#efebe4'), 'refund_requested': ('#8a5a16', '#fff3d6'),
            'refunded': ('#356b3f', '#eaf5e8'),
        }
        foreground, background = palette.get(obj.status, ('#514536', '#f3eee6'))
        return format_html(
            '<span style="display:inline-block;padding:5px 10px;border-radius:99px;background:{};color:{};font-weight:600;white-space:nowrap">{}</span>',
            background, foreground, label,
        )

    @admin.display(description='Thanh toán', ordering='payment_status')
    def payment_status_text(self, obj):
        return ADMIN_CHOICE_LABELS['order', 'payment_status'].get(obj.payment_status, obj.get_payment_status_display())

    @admin.display(description='Tổng tiền')
    def order_total(self, obj):
        return f'${obj.get_total():.2f}'

    @admin.display(description='Ngày đặt hàng', ordering='ordered_date')
    def ordered_date_text(self, obj):
        return obj.ordered_date

    @admin.display(description='Đơn vị vận chuyển', ordering='shipping_carrier')
    def carrier_text(self, obj):
        return obj.shipping_carrier or 'Chưa cập nhật'

    @admin.display(description='Mã vận đơn', ordering='tracking_number')
    def tracking_text(self, obj):
        return obj.tracking_number or 'Chưa cập nhật'

    def get_queryset(self, request):
        return super().get_queryset(request).select_related('user', 'payment').prefetch_related('items__item', 'items__variant')

    def changelist_view(self, request, extra_context=None):
        counts = dict(
            Order.objects.filter(ordered=True)
            .values('status')
            .annotate(total=Count('pk'))
            .values_list('status', 'total')
        )
        extra_context = {
            **(extra_context or {}),
            'order_status_summary': [
                {
                    'value': value,
                    'label': ADMIN_CHOICE_LABELS['order', 'status'].get(value, label),
                    'count': counts.get(value, 0),
                }
                for value, label in Order._meta.get_field('status').choices
            ],
        }
        return super().changelist_view(request, extra_context=extra_context)

    def get_urls(self):
        return [path('sales-report/', self.admin_site.admin_view(self.sales_report), name='core_order_sales_report')] + super().get_urls()

    def sales_report(self, request):
        since = timezone.now() - timedelta(days=30)
        payments = Payment.objects.filter(status='paid')
        status_counts = list(Order.objects.filter(ordered=True).values('status').annotate(total=Count('pk')).order_by('status'))
        for row in status_counts:
            row['status_label'] = ADMIN_CHOICE_LABELS['order', 'status'].get(row['status'], row['status'])
        daily = list(payments.filter(timestamp__gte=since).annotate(day=TruncDate('timestamp')).values('day').annotate(total=Sum('amount')).order_by('day'))
        top_products = list(OrderItem.objects.filter(ordered=True, order__ordered=True, order__status='delivered').values('item__title').annotate(quantity=Sum('quantity')).order_by('-quantity')[:10])
        context = {
            **self.admin_site.each_context(request),
            'title': 'Báo cáo doanh thu và vận hành',
            'paid_revenue': payments.aggregate(total=Sum('amount'))['total'] or 0,
            'paid_orders': Order.objects.filter(ordered=True, payment_status='paid').count(),
            'pending_cod': Order.objects.filter(ordered=True, payment_method='cod', payment_status='pending').count(),
            'pending_cod_amount': Order.objects.filter(ordered=True, payment_method='cod', payment_status='pending').aggregate(total=Sum('payment__amount'))['total'] or 0,
            'status_counts': status_counts,
            'daily_revenue': daily,
            'top_products': top_products,
        }
        return render(request, 'admin/core/order/sales_report.html', context)

    def _bulk_transition(self, request, queryset, target, source_statuses, note):
        updated = 0
        skipped = 0
        for order in queryset.order_by('pk'):
            if order.status not in source_statuses:
                skipped += 1
                continue
            try:
                transition_order_status(order, target, request.user, note)
            except ValidationError:
                skipped += 1
            else:
                updated += 1
        self.message_user(request, f'Đã cập nhật {updated} đơn hàng; bỏ qua {skipped} đơn do trạng thái hiện tại không phù hợp.')

    @admin.action(description='Xác nhận các đơn đang chờ')
    def confirm_selected_orders(self, request, queryset):
        self._bulk_transition(request, queryset, 'confirmed', {'pending'}, 'Nhân viên cửa hàng đã xác nhận đơn.')

    @admin.action(description='Đánh dấu các đơn đã xác nhận là đã đóng gói')
    def pack_selected_orders(self, request, queryset):
        self._bulk_transition(request, queryset, 'packed', {'confirmed'}, 'Nhân viên cửa hàng đã đóng gói đơn.')

    @admin.action(description='Đánh dấu các đơn đã bàn giao cho đơn vị vận chuyển')
    def mark_selected_shipped(self, request, queryset):
        self._bulk_transition(request, queryset, 'shipped', {'packed'}, 'Đơn hàng đã được bàn giao cho đơn vị vận chuyển.')

    @admin.action(description='Ghi nhận giao hàng thất bại')
    def mark_delivery_failed(self, request, queryset):
        self._bulk_transition(request, queryset, 'delivery_failed', {'shipped'}, 'Đơn vị vận chuyển ghi nhận giao hàng thất bại.')

    @admin.action(description='Thử giao lại các đơn giao thất bại')
    def retry_failed_deliveries(self, request, queryset):
        self._bulk_transition(request, queryset, 'shipped', {'delivery_failed'}, 'Shop đã yêu cầu đơn vị vận chuyển thử giao lại.')

    @admin.action(description='Đơn vị vận chuyển đang hoàn kiện về shop')
    def mark_returning_to_shop(self, request, queryset):
        self._bulk_transition(request, queryset, 'returning', {'delivery_failed'}, 'Kiện hàng đang được hoàn về shop sau khi giao thất bại.')

    @admin.action(description='Xác nhận kiện hàng đã về shop và trả tồn kho')
    def mark_returned_to_shop(self, request, queryset):
        self._bulk_transition(request, queryset, 'returned', {'returning'}, 'Shop đã nhận lại kiện hàng giao thất bại; hàng đã được trả lại tồn kho.')

    @admin.action(description='Hủy các đơn đang chờ, đã xác nhận hoặc đã đóng gói')
    def cancel_selected_orders(self, request, queryset):
        self._bulk_transition(request, queryset, 'cancelled', {'pending', 'confirmed', 'packed'}, 'Nhân viên cửa hàng đã hủy đơn.')

    def save_model(self, request, obj, form, change):
        new_status = obj.status
        if change:
            old = Order.objects.get(pk=obj.pk)
            old_total = old.get_total()
            quote_changed = (
                old.shipping_fee != obj.shipping_fee
                or old.shipping_fee_confirmed != obj.shipping_fee_confirmed
            )
            if quote_changed:
                obj.shipping_fee_accepted = False
            obj.status = old.status
            super().save_model(request, obj, form, change)
            if obj.payment_id and obj.get_total() != old_total:
                Payment.objects.filter(pk=obj.payment_id).update(amount=obj.get_total())
            if quote_changed and obj.shipping_fee_confirmed:
                transaction.on_commit(lambda order_id=obj.pk: send_shipping_quote_email(order_id))
            if new_status != old.status:
                try:
                    transition_order_status(
                        obj,
                        new_status,
                        request.user,
                        form.cleaned_data.get('staff_note') or 'Updated by shop staff.',
                    )
                except ValidationError as exc:
                    self.message_user(request, str(exc), level=messages.ERROR)
        else:
            super().save_model(request, obj, form, change)


class ItemVariantInline(VietnameseAdminMixin, admin.TabularInline):
    model = ItemVariant
    extra = 1
    fields = ('size', 'color', 'sku', 'stock_quantity', 'reorder_level', 'is_active')
    show_change_link = True
    can_delete = False


class ItemImageInline(VietnameseAdminMixin, admin.TabularInline):
    model = ItemImage
    extra = 1
    fields = ('image', 'alt_text', 'sort_order')


class PriceHistoryInline(VietnameseAdminMixin, admin.TabularInline):
    model = PriceHistory
    extra = 0
    can_delete = False
    fields = ('old_price', 'new_price', 'old_discount_price', 'new_discount_price', 'changed_at', 'changed_by', 'note')
    readonly_fields = fields

    def has_add_permission(self, request, obj=None):
        return False


class LowStockFilter(admin.SimpleListFilter):
    title = 'Tình trạng tồn kho'
    parameter_name = 'stock_health'

    def lookups(self, request, model_admin):
        return (('low', 'Bằng hoặc thấp hơn mức cần nhập'), ('healthy', 'Trên mức cần nhập'))

    def queryset(self, request, queryset):
        if self.value() not in {'low', 'healthy'}:
            return queryset
        low_variant = ItemVariant.objects.filter(
            item_id=OuterRef('pk'),
            is_active=True,
            stock_quantity__lte=F('reorder_level'),
        )
        active_variant = ItemVariant.objects.filter(item_id=OuterRef('pk'), is_active=True)
        queryset = queryset.annotate(
            _has_low_variant=Exists(low_variant),
            _has_active_variant=Exists(active_variant),
        )
        if self.value() == 'low':
            return queryset.filter(
                Q(_has_low_variant=True)
                | Q(_has_active_variant=False, stock_quantity__lte=F('reorder_level'))
            )
        return queryset.exclude(_has_low_variant=True).filter(
            Q(_has_active_variant=True) | Q(stock_quantity__gt=F('reorder_level'))
        )


@admin.register(Item)
class ItemAdmin(VietnameseAdminMixin, admin.ModelAdmin):
    list_display = ('product_name', 'category_name', 'regular_price', 'sale_price', 'available_stock', 'stock_alert', 'business_status')
    list_filter = ('category', 'is_active', 'label', LowStockFilter)
    search_fields = ('title', 'stock_no', 'category__title')
    prepopulated_fields = {'slug': ('title',)}
    inlines = (ItemVariantInline, ItemImageInline, PriceHistoryInline)

    def get_queryset(self, request):
        return super().get_queryset(request).select_related('category').prefetch_related('variants')

    @admin.display(description='Sản phẩm', ordering='title')
    def product_name(self, obj):
        return obj.title

    @admin.display(description='Danh mục', ordering='category__title')
    def category_name(self, obj):
        return obj.category.title

    @admin.display(description='Giá bán', ordering='price')
    def regular_price(self, obj):
        return f'${obj.price:.2f}'

    @admin.display(description='Giá khuyến mãi', ordering='discount_price')
    def sale_price(self, obj):
        return f'${obj.discount_price:.2f}' if obj.discount_price is not None else '—'

    @admin.display(description='Số lượng có thể bán')
    def available_stock(self, obj):
        return obj.available_stock

    @admin.display(description='Cảnh báo tồn kho')
    def stock_alert(self, obj):
        variants = [variant for variant in obj.variants.all() if variant.is_active]
        if variants:
            low_stock = any(variant.stock_quantity <= variant.reorder_level for variant in variants)
        else:
            low_stock = obj.stock_quantity <= obj.reorder_level
        return 'Cần nhập hàng' if low_stock else 'Đủ hàng'

    @admin.display(description='Trạng thái', ordering='is_active', boolean=True)
    def business_status(self, obj):
        return obj.is_active

    def save_model(self, request, obj, form, change):
        previous = Item.objects.get(pk=obj.pk) if change else None
        old_quantity = previous.stock_quantity if previous else 0
        super().save_model(request, obj, form, change)
        difference = obj.stock_quantity - old_quantity
        if difference:
            StockMovement.objects.create(
                item=obj,
                quantity_change=difference,
                reason='adjustment',
                note='Điều chỉnh tồn kho tại trang quản trị sản phẩm.',
                created_by=request.user,
            )
        price_changed = previous is None or (
            previous.price != obj.price or previous.discount_price != obj.discount_price
        )
        if price_changed:
            PriceHistory.objects.create(
                item=obj,
                old_price=previous.price if previous else None,
                new_price=obj.price,
                old_discount_price=previous.discount_price if previous else None,
                new_discount_price=obj.discount_price,
                changed_by=request.user,
                note='Ghi nhận giá ban đầu' if previous is None else 'Cập nhật giá tại trang quản trị sản phẩm.',
            )

    def save_formset(self, request, form, formset, change):
        if formset.model is not ItemVariant:
            return super().save_formset(request, form, formset, change)
        changed_variants = []
        for variant in formset.save(commit=False):
            old_quantity = ItemVariant.objects.get(pk=variant.pk).stock_quantity if variant.pk else 0
            changed_variants.append((variant, old_quantity))
            variant.save()
        formset.save_m2m()
        for variant, old_quantity in changed_variants:
            difference = variant.stock_quantity - old_quantity
            if difference:
                StockMovement.objects.create(
                    item=variant.item,
                    variant=variant,
                    quantity_change=difference,
                    reason='adjustment',
                    note='Variant stock adjusted in product admin.',
                    created_by=request.user,
                )


@admin.register(ItemVariant)
class ItemVariantAdmin(VietnameseAdminMixin, admin.ModelAdmin):
    list_display = ('sku_label', 'product_label', 'size_label', 'color_label', 'stock_label', 'stock_alert', 'active_label')
    list_filter = ('is_active', 'size', 'color')
    search_fields = ('sku', 'item__title', 'color', 'size')

    @admin.display(description='Mã SKU', ordering='sku')
    def sku_label(self, obj):
        return obj.sku

    @admin.display(description='Sản phẩm', ordering='item__title')
    def product_label(self, obj):
        return obj.item.title

    @admin.display(description='Kích cỡ', ordering='size')
    def size_label(self, obj):
        return obj.size

    @admin.display(description='Màu sắc', ordering='color')
    def color_label(self, obj):
        return obj.color

    @admin.display(description='Tồn kho', ordering='stock_quantity')
    def stock_label(self, obj):
        return obj.stock_quantity

    @admin.display(description='Đang bán', boolean=True, ordering='is_active')
    def active_label(self, obj):
        return obj.is_active

    @admin.display(description='Cảnh báo tồn kho')
    def stock_alert(self, obj):
        return 'Cần nhập hàng' if obj.stock_quantity <= obj.reorder_level else 'Đủ hàng'

    def save_model(self, request, obj, form, change):
        old_quantity = ItemVariant.objects.get(pk=obj.pk).stock_quantity if change else 0
        super().save_model(request, obj, form, change)
        difference = obj.stock_quantity - old_quantity
        if difference:
            StockMovement.objects.create(
                item=obj.item,
                variant=obj,
                quantity_change=difference,
                reason='adjustment',
                note='Điều chỉnh tồn kho biến thể tại trang quản trị.',
                created_by=request.user,
            )


@admin.register(Category)
class CategoryAdmin(VietnameseAdminMixin, admin.ModelAdmin):
    list_display = ('category_name', 'visible_status')
    list_filter = ('is_active',)
    search_fields = ('title',)
    prepopulated_fields = {'slug': ('title',)}

    @admin.display(description='Tên danh mục', ordering='title')
    def category_name(self, obj):
        return obj.title

    @admin.display(description='Đang hiển thị', boolean=True, ordering='is_active')
    def visible_status(self, obj):
        return obj.is_active


@admin.action(description='Đánh dấu yêu cầu đã hoàn tiền')
def approve_return_requests(modeladmin, request, queryset):
    approved = skipped = 0
    for selected in queryset:
        with transaction.atomic():
            refund = Refund.objects.select_for_update().select_related('order').get(pk=selected.pk)
            order = Order.objects.select_for_update().get(pk=refund.order_id)
            if order.status != 'refund_requested' or refund.accepted or refund.rejected:
                skipped += 1
                continue
            refund.accepted = True
            refund.processed_by = request.user
            refund.processed_at = timezone.now()
            refund.save(update_fields=('accepted', 'processed_by', 'processed_at'))
            note = 'Shop approved the return request. Customer may send the items back.'
            OrderStatusHistory.objects.create(order=order, status=order.status, note=note, updated_by=request.user)
            transaction.on_commit(lambda order_id=order.pk, msg=note: send_order_status_email(order_id, 'refund_requested', msg))
            approved += 1
    modeladmin.message_user(request, f'Approved {approved} return requests; skipped {skipped}.')


@admin.action(description='Approve return requests')
def _approve_return_requests_action(modeladmin, request, queryset):
    approve_return_requests(modeladmin, request, queryset)


@admin.action(description='Reject return requests')
def reject_return_requests(modeladmin, request, queryset):
    rejected = skipped = 0
    for selected in queryset:
        try:
            with transaction.atomic():
                refund = Refund.objects.select_for_update().select_related('order').get(pk=selected.pk)
                order = Order.objects.select_for_update().get(pk=refund.order_id)
                if order.status != 'refund_requested' or refund.items_received or refund.rejected:
                    skipped += 1
                    continue
                reason = refund.rejection_reason.strip() or 'Return request declined by shop staff.'
                refund.rejected = True
                refund.accepted = False
                refund.rejection_reason = reason
                refund.processed_by = request.user
                refund.processed_at = timezone.now()
                refund.save(update_fields=('rejected', 'accepted', 'rejection_reason', 'processed_by', 'processed_at'))
                transition_order_status(order, 'delivered', request.user, f'Return request declined: {reason}')
                rejected += 1
        except ValidationError:
            skipped += 1
    modeladmin.message_user(request, f'Rejected {rejected} return requests; skipped {skipped}.')


@admin.action(description='Mark approved refunds as paid')
def mark_refunds_complete(modeladmin, request, queryset):
    completed = skipped = 0
    for selected in queryset:
        try:
            with transaction.atomic():
                refund = Refund.objects.select_for_update().select_related('order').get(pk=selected.pk)
                order = Order.objects.select_for_update().get(pk=refund.order_id)
                if (
                    order.status != 'refund_requested' or not refund.accepted or not refund.items_received
                    or not refund.refund_method
                    or (refund.refund_method == 'bank_transfer' and not refund.refund_reference)
                ):
                    skipped += 1
                    continue
                refund.refund_amount = order.get_total()
                refund.refunded_by = request.user
                refund.refunded_at = timezone.now()
                refund.save(update_fields=('refund_amount', 'refunded_by', 'refunded_at'))
                note = f'Refund of ${refund.refund_amount:.2f} completed by {refund.get_refund_method_display()}.'
                if refund.refund_reference:
                    note += f' Reference: {refund.refund_reference}.'
                transition_order_status(order, 'refunded', request.user, note)
                completed += 1
        except ValidationError:
            skipped += 1
    modeladmin.message_user(request, f'Completed {completed} refunds; skipped {skipped}.')


@admin.action(description='Restock items from completed returns')
def restock_returned_items(modeladmin, request, queryset):
    restocked_count = skipped = 0
    for selected in queryset:
        with transaction.atomic():
            refund = Refund.objects.select_for_update().select_related('order').get(pk=selected.pk)
            if not refund.accepted or not refund.items_received or refund.restocked or refund.order.status != 'refunded':
                skipped += 1
                continue
            order = Order.objects.select_for_update().get(pk=refund.order_id)
            for line in order.items.select_related('item', 'variant'):
                if line.variant_id:
                    ItemVariant.objects.filter(pk=line.variant_id).update(stock_quantity=F('stock_quantity') + line.quantity)
                else:
                    Item.objects.filter(pk=line.item_id).update(stock_quantity=F('stock_quantity') + line.quantity)
                StockMovement.objects.create(
                    item_id=line.item_id, variant=line.variant, order=order, quantity_change=line.quantity,
                    reason='refund_return', note=f'Returned goods received for refund {refund.pk}.', created_by=request.user,
                )
            order.stock_deducted = False
            order.save(update_fields=('stock_deducted',))
            refund.restocked = True
            refund.save(update_fields=('restocked',))
            restocked_count += 1
    modeladmin.message_user(request, f'Restocked {restocked_count} returns; skipped {skipped}.')


@admin.register(Refund)
class RefundAdmin(VietnameseAdminMixin, admin.ModelAdmin):
    list_display = ('order_label', 'email_label', 'accepted_label', 'received_label', 'rejected_label', 'restocked_label', 'refund_amount_label', 'processed_at_label')
    list_filter = ('accepted', 'items_received', 'rejected', 'restocked')
    search_fields = ('order__ref_code', 'email')
    readonly_fields = ('order', 'email', 'reason', 'accepted', 'rejected', 'restocked', 'processed_by', 'processed_at', 'refund_amount', 'refunded_by', 'refunded_at')
    actions = (_approve_return_requests_action, reject_return_requests, mark_refunds_complete, restock_returned_items)
    fieldsets = (
        ('Return request', {'fields': ('order', 'email', 'reason', 'accepted', 'rejected', 'rejection_reason')}),
        ('Returned parcel', {'fields': ('items_received', 'restocked')}),
        ('Manual refund record', {'fields': ('refund_method', 'refund_reference', 'refund_amount', 'refunded_by', 'refunded_at')}),
        ('Processing', {'fields': ('processed_by', 'processed_at')}),
    )

    @admin.display(description='Order', ordering='order__ref_code')
    def order_label(self, obj):
        return obj.order.ref_code

    @admin.display(description='Customer email', ordering='email')
    def email_label(self, obj):
        return obj.email

    @admin.display(description='Approved', boolean=True, ordering='accepted')
    def accepted_label(self, obj):
        return obj.accepted

    @admin.display(description='Parcel received', boolean=True, ordering='items_received')
    def received_label(self, obj):
        return obj.items_received

    @admin.display(description='Rejected', boolean=True, ordering='rejected')
    def rejected_label(self, obj):
        return obj.rejected

    @admin.display(description='Restocked', boolean=True, ordering='restocked')
    def restocked_label(self, obj):
        return obj.restocked

    @admin.display(description='Refund amount', ordering='refund_amount')
    def refund_amount_label(self, obj):
        return f'${obj.refund_amount:.2f}' if obj.refund_amount is not None else 'Not refunded'

    @admin.display(description='Processed at', ordering='processed_at')
    def processed_at_label(self, obj):
        return obj.processed_at or 'Not processed'

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return False

    def save_model(self, request, obj, form, change):
        if obj.items_received and not obj.accepted:
            raise ValidationError('Approve the return before marking the parcel as received.')
        if obj.items_received and obj.order.status != 'refund_requested':
            raise ValidationError('The order must still be awaiting its return before recording parcel arrival.')
        super().save_model(request, obj, form, change)


@admin.register(Slide)
class SlideAdmin(VietnameseAdminMixin, admin.ModelAdmin):
    list_display = ('title_label', 'subtitle_label', 'visible_label')
    list_filter = ('is_active',)
    search_fields = ('caption1', 'caption2')

    @admin.display(description='Tiêu đề nhỏ', ordering='caption1')
    def title_label(self, obj):
        return obj.caption1

    @admin.display(description='Tiêu đề chính', ordering='caption2')
    def subtitle_label(self, obj):
        return obj.caption2

    @admin.display(description='Đang hiển thị', boolean=True, ordering='is_active')
    def visible_label(self, obj):
        return obj.is_active


@admin.register(Review)
class ReviewAdmin(VietnameseAdminMixin, admin.ModelAdmin):
    list_display = ('product_label', 'customer_label', 'rating_label', 'created_label', 'verified_label')
    list_filter = ('rating', 'created_at')
    search_fields = ('item__title', 'user__username', 'comment')
    readonly_fields = ('created_at',)

    @admin.display(description='Sản phẩm', ordering='item__title')
    def product_label(self, obj):
        return obj.item.title

    @admin.display(description='Khách hàng', ordering='user__username')
    def customer_label(self, obj):
        return obj.user.get_full_name() or obj.user.username

    @admin.display(description='Số sao', ordering='rating')
    def rating_label(self, obj):
        return f'{obj.rating}/5'

    @admin.display(description='Ngày đánh giá', ordering='created_at')
    def created_label(self, obj):
        return obj.created_at

    @admin.display(description='Đã mua hàng', boolean=True)
    def verified_label(self, obj):
        return obj.verified_purchase


@admin.register(Supplier)
class SupplierAdmin(VietnameseAdminMixin, admin.ModelAdmin):
    list_display = ('name_label', 'contact_label', 'email_label', 'phone_label', 'active_label')
    list_filter = ('is_active',)
    search_fields = ('name', 'contact_name', 'email', 'phone')

    @admin.display(description='Nhà cung cấp', ordering='name')
    def name_label(self, obj):
        return obj.name

    @admin.display(description='Người liên hệ', ordering='contact_name')
    def contact_label(self, obj):
        return obj.contact_name or '—'

    @admin.display(description='Email', ordering='email')
    def email_label(self, obj):
        return obj.email or '—'

    @admin.display(description='Điện thoại', ordering='phone')
    def phone_label(self, obj):
        return obj.phone or '—'

    @admin.display(description='Đang hợp tác', boolean=True, ordering='is_active')
    def active_label(self, obj):
        return obj.is_active


@admin.register(StockReceipt)
class StockReceiptAdmin(VietnameseAdminMixin, admin.ModelAdmin):
    list_display = ('reference_label', 'supplier_label', 'item_label', 'variant_label', 'quantity_label', 'unit_cost_label', 'total_cost_label', 'received_at_label', 'received_by_label')
    list_filter = ('received_at', 'supplier')
    search_fields = ('reference', 'item__title', 'variant__sku', 'supplier__name')
    readonly_fields = ('received_at', 'received_by', 'total_cost')
    autocomplete_fields = ('supplier', 'item', 'variant')

    @admin.display(description='Mã phiếu nhập', ordering='reference')
    def reference_label(self, obj):
        return obj.reference or '—'

    @admin.display(description='Nhà cung cấp', ordering='supplier__name')
    def supplier_label(self, obj):
        return obj.supplier.name

    @admin.display(description='Sản phẩm', ordering='item__title')
    def item_label(self, obj):
        return obj.item.title

    @admin.display(description='Biến thể')
    def variant_label(self, obj):
        return obj.variant or '—'

    @admin.display(description='Số lượng', ordering='quantity')
    def quantity_label(self, obj):
        return obj.quantity

    @admin.display(description='Giá nhập', ordering='unit_cost')
    def unit_cost_label(self, obj):
        return f'${obj.unit_cost:.2f}'

    @admin.display(description='Thành tiền')
    def total_cost_label(self, obj):
        return f'${obj.total_cost:.2f}'

    @admin.display(description='Ngày nhập kho', ordering='received_at')
    def received_at_label(self, obj):
        return obj.received_at

    @admin.display(description='Người nhận', ordering='received_by__username')
    def received_by_label(self, obj):
        return obj.received_by or '—'

    def has_change_permission(self, request, obj=None):
        return obj is None and super().has_change_permission(request, obj)

    def save_model(self, request, obj, form, change):
        if change:
            raise ValidationError('Phiếu nhập đã ghi nhận không thể sửa; hãy tạo phiếu điều chỉnh để sửa sai.')
        obj.received_by = request.user
        obj.full_clean()
        with transaction.atomic():
            super().save_model(request, obj, form, change)
            if obj.variant_id:
                ItemVariant.objects.filter(pk=obj.variant_id).update(stock_quantity=F('stock_quantity') + obj.quantity)
            else:
                Item.objects.filter(pk=obj.item_id).update(stock_quantity=F('stock_quantity') + obj.quantity)
            StockMovement.objects.create(
                item=obj.item, variant=obj.variant, quantity_change=obj.quantity,
                reason='purchase', note=f'Nhập hàng từ nhà cung cấp {obj.reference}'.strip(), created_by=request.user,
            )

    def has_delete_permission(self, request, obj=None):
        return False
@admin.register(Payment)
class PaymentAdmin(VietnameseAdminMixin, admin.ModelAdmin):
    list_display = ('timestamp_label', 'customer_label', 'method_label', 'status_label', 'amount_label', 'transaction_label')
    list_filter = ('method', 'status', 'timestamp')
    search_fields = ('user__username', 'stripe_charge_id')
    readonly_fields = tuple(field.name for field in Payment._meta.fields)

    @admin.display(description='Thời điểm', ordering='timestamp')
    def timestamp_label(self, obj):
        return obj.timestamp

    @admin.display(description='Khách hàng', ordering='user__username')
    def customer_label(self, obj):
        return obj.user or '—'

    @admin.display(description='Phương thức', ordering='method')
    def method_label(self, obj):
        return ADMIN_CHOICE_LABELS['payment', 'method'].get(obj.method, obj.get_method_display())

    @admin.display(description='Trạng thái', ordering='status')
    def status_label(self, obj):
        return ADMIN_CHOICE_LABELS['payment', 'status'].get(obj.status, obj.get_status_display())

    @admin.display(description='Số tiền', ordering='amount')
    def amount_label(self, obj):
        return f'${obj.amount:.2f}'

    @admin.display(description='Mã giao dịch', ordering='stripe_charge_id')
    def transaction_label(self, obj):
        return obj.stripe_charge_id or '—'

    def has_add_permission(self, request):
        # Payments are created by checkout and updated by the order workflow.
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False

@admin.register(BillingAddress)
class BillingAddressAdmin(VietnameseAdminMixin, admin.ModelAdmin):
    list_display = ('recipient_name', 'user', 'phone_number', 'street_address', 'default')
    search_fields = ('recipient_name', 'phone_number', 'street_address', 'user__username', 'user__email')


@admin.register(Coupon)
class CouponAdmin(VietnameseAdminMixin, admin.ModelAdmin):
    list_display = ('code_label', 'amount_label', 'minimum_label', 'active_label', 'expires_label', 'used_label', 'limit_label')
    list_filter = ('is_active', 'expires_at')
    search_fields = ('code',)

    @admin.display(description='Mã giảm giá', ordering='code')
    def code_label(self, obj):
        return obj.code

    @admin.display(description='Mức giảm', ordering='amount')
    def amount_label(self, obj):
        return f'${obj.amount:.2f}'

    @admin.display(description='Đơn tối thiểu', ordering='minimum_order_amount')
    def minimum_label(self, obj):
        return f'${obj.minimum_order_amount:.2f}'

    @admin.display(description='Đang hoạt động', boolean=True, ordering='is_active')
    def active_label(self, obj):
        return obj.is_active

    @admin.display(description='Hết hạn lúc', ordering='expires_at')
    def expires_label(self, obj):
        return obj.expires_at or 'Không thời hạn'

    @admin.display(description='Đã sử dụng', ordering='use_count')
    def used_label(self, obj):
        return obj.use_count

    @admin.display(description='Giới hạn lượt dùng', ordering='max_uses')
    def limit_label(self, obj):
        return obj.max_uses or 'Không giới hạn'
@admin.register(StockMovement)
class StockMovementAdmin(VietnameseAdminMixin, admin.ModelAdmin):
    list_display = ('created_at_label', 'item_label', 'variant_label', 'quantity_label', 'reason_label', 'order_label', 'actor_label')
    list_filter = ('reason', 'created_at')
    search_fields = ('item__title', 'variant__sku', 'order__ref_code', 'note')
    readonly_fields = ('item', 'variant', 'order', 'quantity_change', 'reason', 'note', 'created_by', 'created_at')

    @admin.display(description='Thời điểm', ordering='created_at')
    def created_at_label(self, obj):
        return obj.created_at

    @admin.display(description='Sản phẩm', ordering='item__title')
    def item_label(self, obj):
        return obj.item.title

    @admin.display(description='Biến thể')
    def variant_label(self, obj):
        return obj.variant or '—'

    @admin.display(description='Thay đổi tồn kho', ordering='quantity_change')
    def quantity_label(self, obj):
        return f'{obj.quantity_change:+d}'

    @admin.display(description='Lý do', ordering='reason')
    def reason_label(self, obj):
        translations = ADMIN_CHOICE_LABELS['stockmovement', 'reason']
        return translations.get(obj.reason, obj.get_reason_display())

    @admin.display(description='Mã đơn', ordering='order__ref_code')
    def order_label(self, obj):
        return obj.order.ref_code if obj.order else '—'

    @admin.display(description='Người thực hiện', ordering='created_by__username')
    def actor_label(self, obj):
        return obj.created_by or '—'

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False
