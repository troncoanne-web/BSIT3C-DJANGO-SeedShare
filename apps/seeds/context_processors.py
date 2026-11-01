from .models import SeedOrder, SeedTradeRequest


def pending_seed_orders(request):
    count = 0
    if request.user.is_authenticated:
        count = SeedOrder.objects.filter(
            entry__user=request.user,
            status=SeedOrder.Status.PENDING,
        ).count()
        count += SeedTradeRequest.objects.filter(
            entry__user=request.user,
            status=SeedTradeRequest.Status.PENDING,
        ).count()
    return {'pending_seed_request_count': count}
