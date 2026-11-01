from django.urls import path

from . import views

app_name = 'seeds'

urlpatterns = [
    path('', views.seed_list, name='list'),
    path('add/', views.seed_create, name='create'),
    path('my-posts/', views.my_seed_entries, name='my_posts'),
    path('orders/', views.seed_orders, name='orders'),
    path('orders/<int:pk>/complete/', views.seed_order_complete, name='order_complete'),
    path('orders/<int:pk>/<str:action>/', views.seed_order_action, name='order_action'),
    path('trades/<int:pk>/<str:action>/', views.seed_trade_action, name='trade_action'),
    path('<int:pk>/order/', views.seed_order, name='order'),
    path('<int:pk>/trade/', views.seed_trade_request, name='trade_request'),
    path('<int:pk>/rate/', views.seed_rate, name='rate'),
    path('<int:pk>/edit/', views.seed_edit, name='edit'),
    path('<int:pk>/delete/', views.seed_delete, name='delete'),
    path('<int:pk>/', views.seed_detail, name='detail'),
]
