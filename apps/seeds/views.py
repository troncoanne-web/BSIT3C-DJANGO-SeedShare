from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db import transaction
from django.db.models import Avg, Count, F, IntegerField, OuterRef, Q, Subquery, Sum, Value
from django.db.models.functions import Coalesce
from django.http import Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST, require_http_methods

from .forms import SeedEntryForm, SeedOrderForm, SeedRatingForm, SeedTradeRequestForm
from .models import SeedEntry, SeedOrder, SeedRating, SeedTradeRequest


def _available_quantity(entry):
    accepted_quantity = SeedOrder.objects.filter(
        entry=entry,
        status__in=[SeedOrder.Status.ACCEPTED, SeedOrder.Status.COMPLETED],
    ).aggregate(total=Sum('quantity'))['total'] or 0
    traded_quantity = SeedTradeRequest.objects.filter(
        entry=entry,
        status=SeedTradeRequest.Status.COMPLETED,
    ).aggregate(total=Sum('quantity'))['total'] or 0
    return max(0, entry.quantity - accepted_quantity - traded_quantity)


def _available_quantity_expression():
    accepted_orders = (
        SeedOrder.objects.filter(
            entry_id=OuterRef('pk'),
            status__in=[SeedOrder.Status.ACCEPTED, SeedOrder.Status.COMPLETED],
        )
        .order_by()
        .values('entry_id')
        .annotate(total=Sum('quantity'))
        .values('total')[:1]
    )
    completed_trades = (
        SeedTradeRequest.objects.filter(
            entry_id=OuterRef('pk'),
            status=SeedTradeRequest.Status.COMPLETED,
        )
        .order_by()
        .values('entry_id')
        .annotate(total=Sum('quantity'))
        .values('total')[:1]
    )
    return (
        F('quantity')
        - Coalesce(Subquery(accepted_orders, output_field=IntegerField()), Value(0))
        - Coalesce(Subquery(completed_trades, output_field=IntegerField()), Value(0))
    )


def _is_tradeable_entry(entry):
    return (
        entry.kind == SeedEntry.Kind.WANT
        or (
            entry.kind == SeedEntry.Kind.HAVE
            and entry.offer_type == SeedEntry.OfferType.TRADE
        )
    )


def _user_completed_transaction(entry, user):
    if not user.is_authenticated:
        return False
    return (
        SeedOrder.objects.filter(
            entry=entry,
            status=SeedOrder.Status.COMPLETED,
        )
        .filter(Q(buyer=user) | Q(entry__user=user))
        .exists()
        or SeedTradeRequest.objects.filter(
            entry=entry,
            status=SeedTradeRequest.Status.COMPLETED,
        )
        .filter(Q(requester=user) | Q(entry__user=user))
        .exists()
    )


def seed_list(request):
    entries = (
        SeedEntry.objects.select_related('user')
        .prefetch_related('images')
        .annotate(rating_average=Avg('ratings__score'), rating_count=Count('ratings'))
        .annotate(available_quantity=_available_quantity_expression())
    )
    kind = request.GET.get('kind', '')
    query = request.GET.get('q', '').strip()
    if kind in SeedEntry.Kind.values:
        entries = entries.filter(kind=kind)
    if query:
        entries = entries.filter(
            Q(name__icontains=query)
            | Q(variety__icontains=query)
            | Q(description__icontains=query)
            | Q(location__icontains=query)
            | Q(trade_for__icontains=query)
        )

    return render(request, 'seeds/list.html', {
        'entries': entries,
        'selected_kind': kind,
        'search_query': query,
    })


def seed_detail(request, pk):
    entry = get_object_or_404(
        SeedEntry.objects.select_related('user')
        .prefetch_related('images', 'ratings__user')
        .annotate(rating_average=Avg('ratings__score'), rating_count=Count('ratings'))
        .annotate(available_quantity=_available_quantity_expression()),
        pk=pk,
    )
    existing_rating = None
    rating_form = None
    can_rate = _user_completed_transaction(entry, request.user)
    if can_rate:
        existing_rating = SeedRating.objects.filter(
            entry=entry,
            user=request.user,
        ).first()
        rating_form = SeedRatingForm(instance=existing_rating)
    return render(request, 'seeds/detail.html', {
        'entry': entry,
        'can_rate': can_rate,
        'existing_rating': existing_rating,
        'rating_form': rating_form,
    })


@login_required(login_url='login')
def my_seed_entries(request):
    entries = (
        SeedEntry.objects.filter(user=request.user)
        .prefetch_related('images')
        .annotate(rating_average=Avg('ratings__score'), rating_count=Count('ratings'))
        .annotate(available_quantity=_available_quantity_expression())
    )
    return render(request, 'seeds/my_posts.html', {'entries': entries})


@login_required(login_url='login')
def seed_create(request):
    form = SeedEntryForm(
        request.POST if request.method == 'POST' else None,
        request.FILES if request.method == 'POST' else None,
    )

    if request.method == 'POST' and form.is_valid():
        entry = form.save(commit=False)
        entry.user = request.user
        entry.save()
        form.save_images(entry)
        messages.success(request, f'{entry.get_kind_display()} "{entry.name}" added.')
        return redirect('seeds:list')

    return render(request, 'seeds/create.html', {'form': form, 'is_edit': False})


@login_required(login_url='login')
@require_http_methods(['GET', 'POST'])
def seed_edit(request, pk):
    if request.method == 'POST':
        with transaction.atomic():
            entry = get_object_or_404(
                SeedEntry.objects.select_for_update(),
                pk=pk,
                user=request.user,
            )
            form = SeedEntryForm(request.POST, request.FILES, instance=entry)
            if form.is_valid():
                accepted_quantity = SeedOrder.objects.filter(
                    entry=entry,
                    status__in=[SeedOrder.Status.ACCEPTED, SeedOrder.Status.COMPLETED],
                ).aggregate(total=Sum('quantity'))['total'] or 0
                accepted_quantity += SeedTradeRequest.objects.filter(
                    entry=entry,
                    status=SeedTradeRequest.Status.COMPLETED,
                ).aggregate(total=Sum('quantity'))['total'] or 0
                if form.cleaned_data['quantity'] < accepted_quantity:
                    form.add_error(
                        'quantity',
                        f'Quantity cannot be lower than the {accepted_quantity} {entry.unit} already sold or traded.',
                    )
                else:
                    entry = form.save()
                    form.save_images(entry)
                    messages.success(request, f'"{entry.name}" was updated.')
                    return redirect('seeds:my_posts')
    else:
        entry = get_object_or_404(SeedEntry, pk=pk, user=request.user)
        form = SeedEntryForm(instance=entry)

    return render(request, 'seeds/create.html', {
        'form': form,
        'is_edit': True,
        'entry': entry,
    })


@login_required(login_url='login')
@require_POST
def seed_delete(request, pk):
    with transaction.atomic():
        entry = get_object_or_404(
            SeedEntry.objects.select_for_update(),
            pk=pk,
            user=request.user,
        )
        if entry.orders.exists() or entry.trade_requests.exists():
            messages.error(request, 'This post cannot be deleted because it has transaction history.')
            return redirect('seeds:my_posts')
        name = entry.name
        entry.delete()
    messages.success(request, f'"{name}" was deleted.')
    return redirect('seeds:my_posts')


@login_required(login_url='login')
@require_http_methods(['GET', 'POST'])
def seed_order(request, pk):
    if request.method == 'POST':
        with transaction.atomic():
            entry = get_object_or_404(
                SeedEntry.objects.select_for_update(),
                pk=pk,
                kind=SeedEntry.Kind.HAVE,
                offer_type=SeedEntry.OfferType.SALE,
                price__isnull=False,
            )
            if entry.user_id == request.user.pk:
                raise Http404

            available_quantity = _available_quantity(entry)
            form = SeedOrderForm(
                request.POST,
                entry=entry,
                available_quantity=available_quantity,
            )
            if available_quantity and form.is_valid():
                quantity = form.cleaned_data['quantity']
                SeedOrder.objects.create(
                    entry=entry,
                    buyer=request.user,
                    quantity=quantity,
                    delivery_address=form.cleaned_data['delivery_address'],
                    total_price=entry.price_for_quantity(quantity),
                )
                messages.success(request, 'Your order request was sent to the seller.')
                return redirect('seeds:orders')
    else:
        entry = get_object_or_404(
            SeedEntry.objects.select_related('user'),
            pk=pk,
            kind=SeedEntry.Kind.HAVE,
            offer_type=SeedEntry.OfferType.SALE,
            price__isnull=False,
        )
        if entry.user_id == request.user.pk:
            raise Http404
        available_quantity = _available_quantity(entry)
        form = SeedOrderForm(
            entry=entry,
            available_quantity=available_quantity,
        )

    if not available_quantity:
        messages.error(request, 'This post is currently out of stock.')
        return redirect('seeds:detail', pk=pk)

    return render(request, 'seeds/order.html', {
        'entry': entry,
        'form': form,
        'available_quantity': available_quantity,
    })


@login_required(login_url='login')
def seed_orders(request):
    incoming_orders = SeedOrder.objects.filter(
        entry__user=request.user,
    ).select_related('entry', 'buyer')
    outgoing_orders = SeedOrder.objects.filter(
        buyer=request.user,
    ).select_related('entry', 'entry__user')
    incoming_trades = SeedTradeRequest.objects.filter(
        entry__user=request.user,
    ).select_related('entry', 'requester')
    outgoing_trades = SeedTradeRequest.objects.filter(
        requester=request.user,
    ).select_related('entry', 'entry__user')
    return render(request, 'seeds/orders.html', {
        'incoming_orders': incoming_orders,
        'outgoing_orders': outgoing_orders,
        'incoming_trades': incoming_trades,
        'outgoing_trades': outgoing_trades,
    })


@login_required(login_url='login')
@require_POST
def seed_order_action(request, pk, action):
    if action not in {'accept', 'reject'}:
        raise Http404

    order = get_object_or_404(
        SeedOrder,
        pk=pk,
        entry__user=request.user,
    )

    with transaction.atomic():
        order = SeedOrder.objects.select_for_update().get(pk=order.pk)
        entry = SeedEntry.objects.select_for_update().get(pk=order.entry_id)

        if order.status != SeedOrder.Status.PENDING:
            messages.error(request, 'This order has already been processed.')
        elif action == 'accept':
            if order.quantity > _available_quantity(entry):
                messages.error(
                    request,
                    'There is not enough stock to accept this order. Reject it or edit your post.',
                )
            else:
                order.status = SeedOrder.Status.ACCEPTED
                order.save(update_fields=['status', 'updated_at'])
                messages.success(request, 'The order was accepted.')
        elif action == 'reject':
            order.status = SeedOrder.Status.REJECTED
            order.save(update_fields=['status', 'updated_at'])
            messages.success(request, 'The order was rejected.')

    return redirect('seeds:orders')


@login_required(login_url='login')
@require_POST
def seed_order_complete(request, pk):
    with transaction.atomic():
        order = get_object_or_404(
            SeedOrder.objects.select_for_update(),
            Q(buyer=request.user) | Q(entry__user=request.user),
            pk=pk,
        )
        entry = SeedEntry.objects.select_for_update().get(pk=order.entry_id)

        if order.status != SeedOrder.Status.ACCEPTED:
            messages.error(request, 'Only accepted orders can be marked complete.')
        elif order.buyer_id == request.user.pk:
            if order.buyer_confirmed_completion:
                messages.error(request, 'You have already confirmed this order.')
            else:
                order.buyer_confirmed_completion = True
                messages.success(request, 'You confirmed the order is complete.')
        elif entry.user_id == request.user.pk:
            if order.seller_confirmed_completion:
                messages.error(request, 'You have already confirmed this order.')
            else:
                order.seller_confirmed_completion = True
                messages.success(request, 'You confirmed the order is complete.')

        if (
            order.status == SeedOrder.Status.ACCEPTED
            and order.buyer_confirmed_completion
            and order.seller_confirmed_completion
        ):
            order.status = SeedOrder.Status.COMPLETED
            messages.success(request, 'The order is complete. You can now rate this post.')

        order.save(update_fields=[
            'buyer_confirmed_completion',
            'seller_confirmed_completion',
            'status',
            'updated_at',
        ])

    return redirect('seeds:orders')


@login_required(login_url='login')
@require_http_methods(['GET', 'POST'])
def seed_trade_request(request, pk):
    if request.method == 'POST':
        with transaction.atomic():
            entry = get_object_or_404(
                SeedEntry.objects.select_for_update(),
                pk=pk,
            )
            if not _is_tradeable_entry(entry) or entry.user_id == request.user.pk:
                raise Http404
            available_quantity = _available_quantity(entry)
            form = SeedTradeRequestForm(
                request.POST,
                entry=entry,
                available_quantity=available_quantity,
            )
            if available_quantity and form.is_valid():
                SeedTradeRequest.objects.create(
                    entry=entry,
                    requester=request.user,
                    quantity=form.cleaned_data['quantity'],
                    offer_description=form.cleaned_data['offer_description'],
                )
                messages.success(request, 'Your trade request was sent to the post owner.')
                return redirect('seeds:orders')
    else:
        entry = get_object_or_404(SeedEntry.objects.select_related('user'), pk=pk)
        if not _is_tradeable_entry(entry) or entry.user_id == request.user.pk:
            raise Http404
        available_quantity = _available_quantity(entry)
        form = SeedTradeRequestForm(
            entry=entry,
            available_quantity=available_quantity,
        )

    if not available_quantity:
        messages.error(request, 'This post has no remaining quantity.')
        return redirect('seeds:detail', pk=pk)

    return render(request, 'seeds/trade_request.html', {
        'entry': entry,
        'form': form,
        'available_quantity': available_quantity,
    })


@login_required(login_url='login')
@require_POST
def seed_trade_action(request, pk, action):
    if action not in {'accept', 'reject', 'complete'}:
        raise Http404

    if action == 'complete':
        access_filter = Q(requester=request.user) | Q(entry__user=request.user)
    else:
        access_filter = Q(entry__user=request.user)

    with transaction.atomic():
        trade_request = get_object_or_404(
            SeedTradeRequest.objects.select_for_update(),
            access_filter,
            pk=pk,
        )
        entry = SeedEntry.objects.select_for_update().get(pk=trade_request.entry_id)

        if action in {'accept', 'reject'}:
            if trade_request.status != SeedTradeRequest.Status.PENDING:
                messages.error(request, 'This trade request has already been processed.')
            elif action == 'accept':
                trade_request.status = SeedTradeRequest.Status.ACCEPTED
                messages.success(request, 'The trade request was accepted.')
            else:
                trade_request.status = SeedTradeRequest.Status.REJECTED
                messages.success(request, 'The trade request was rejected.')
        elif trade_request.status != SeedTradeRequest.Status.ACCEPTED:
            messages.error(request, 'Only accepted trade requests can be marked complete.')
        else:
            if trade_request.requester_id == request.user.pk:
                if trade_request.requester_confirmed_completion:
                    messages.error(request, 'You have already confirmed this trade.')
                else:
                    trade_request.requester_confirmed_completion = True
                    messages.success(request, 'You confirmed the trade is complete.')
            elif entry.user_id == request.user.pk:
                if trade_request.owner_confirmed_completion:
                    messages.error(request, 'You have already confirmed this trade.')
                else:
                    trade_request.owner_confirmed_completion = True
                    messages.success(request, 'You confirmed the trade is complete.')

            both_confirmed = (
                trade_request.requester_confirmed_completion
                and trade_request.owner_confirmed_completion
            )
            if both_confirmed:
                if trade_request.quantity > _available_quantity(entry):
                    messages.error(
                        request,
                        'There is not enough quantity to complete this trade.',
                    )
                    if trade_request.requester_id == request.user.pk:
                        trade_request.requester_confirmed_completion = False
                    else:
                        trade_request.owner_confirmed_completion = False
                else:
                    trade_request.status = SeedTradeRequest.Status.COMPLETED
                    messages.success(request, 'The trade is complete. You can now rate this post.')

        trade_request.save(update_fields=[
            'status',
            'requester_confirmed_completion',
            'owner_confirmed_completion',
            'updated_at',
        ])

    return redirect('seeds:orders')


@login_required(login_url='login')
@require_POST
def seed_rate(request, pk):
    with transaction.atomic():
        entry = get_object_or_404(SeedEntry.objects.select_for_update(), pk=pk)
        if not _user_completed_transaction(entry, request.user):
            messages.error(request, 'Only participants in a completed order or trade can rate this post.')
            return redirect('seeds:detail', pk=pk)

        existing_rating = SeedRating.objects.filter(entry=entry, user=request.user).first()
        form = SeedRatingForm(request.POST, instance=existing_rating)
        if form.is_valid():
            rating = form.save(commit=False)
            rating.entry = entry
            rating.user = request.user
            rating.save()
            messages.success(request, 'Your rating was saved.')
        else:
            messages.error(request, 'Choose a star rating from 1 to 5.')

    return redirect('seeds:detail', pk=pk)
