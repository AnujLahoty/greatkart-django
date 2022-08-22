from django.http import HttpResponse, JsonResponse
from django.shortcuts import render, redirect
from carts.models import CartItem
from .forms import OrderForm
from .models import Order, Payment, OrderProduct
import datetime
import json
from store.models import Product
from django.core.mail import EmailMessage
from django.template.loader import render_to_string
from django.db.models import Count, Sum, Avg
from django.utils import timezone
# Create your views here.

def payments(request):
    body = json.loads(request.body)
    order = Order.objects.get(user=request.user, is_ordered=False, order_number=body['orderID'])

    # Store transaction details inside Payment model
    payment = Payment(
        user = request.user,
        payment_id = body['transID'],
        payment_method = body['payment_method'],
        amount_paid = order.order_total,
        status = body['status'],
    )
    payment.save()

    order.payment = payment
    order.is_ordered = True
    order.save()

    # Move the cart items to Order Product table
    cart_items = CartItem.objects.filter(user=request.user)

    for item in cart_items:
        orderproduct = OrderProduct()
        orderproduct.order_id = order.id
        orderproduct.payment = payment
        orderproduct.user_id = request.user.id
        orderproduct.product_id = item.product_id
        orderproduct.quantity = item.quantity
        orderproduct.product_price = item.product.price
        orderproduct.ordered = True
        orderproduct.save()
        
        cart_item = CartItem.objects.get(id=item.id)
        product_variation = cart_item.variations.all()
        orderproduct = OrderProduct.objects.get(id=orderproduct.id)
        orderproduct.variations.set(product_variation)
        orderproduct.save()
        
        # Reduce the quantity of the sold products
        product = Product.objects.get(id=item.product_id)
        product.stock -= item.quantity
        product.save()

    # Clear cart
    CartItem.objects.filter(user=request.user).delete()
    
    # Send order recieved email to customer
    mail_subject = 'Thank you for your order!'
    message = render_to_string('orders/order_recieved_email.html', {
        'user': request.user,
        'order': order,
    })
    to_email = request.user.email
    print("Email will be sent to ", to_email)
    send_email = EmailMessage(mail_subject, message, to=[to_email])
    send_email.send()
        
    # Send order number and transaction id back to sendData method via JsonResponse
    data = {
        'order_number': order.order_number,
        'transID': payment.payment_id,
    }
    return JsonResponse(data)

def place_order(request):
    current_user = request.user
    
    # If cart items are 0 then redirect user to store page
    
    cart_items = CartItem.objects.filter(user=current_user)
    cart_count = cart_items.count()
    
    if cart_count <= 0:
        return redirect('store')
    
    grand_total = 0
    tax = 0
    total = 0
    quantity = 0
    for cart_item in cart_items:
        total += (cart_item.product.price * cart_item.quantity)
        quantity += cart_item.quantity
    tax = (2 * total)/100
    grand_total = total + tax
    
    if request.method == 'POST':
        form = OrderForm(request.POST)
        if form.is_valid():
            data = Order()
            data.user = current_user
            data.first_name = form.cleaned_data['first_name']
            data.last_name = form.cleaned_data['last_name']
            data.phone = form.cleaned_data['phone']
            data.email = form.cleaned_data['email']
            data.address_line_1 = form.cleaned_data['address_line_1']
            data.address_line_2 = form.cleaned_data['address_line_2']
            data.country = form.cleaned_data['country']
            data.state = form.cleaned_data['state']
            data.city = form.cleaned_data['city']
            data.order_note = form.cleaned_data['order_note']
            data.order_total = grand_total
            data.tax = tax
            data.ip = request.META.get('REMOTE_ADDR')
            data.save()
            # Generate order number
            yr = int(datetime.date.today().strftime('%Y'))
            dt = int(datetime.date.today().strftime('%d'))
            mt = int(datetime.date.today().strftime('%m'))
            d = datetime.date(yr,mt,dt)
            current_date = d.strftime("%Y%m%d") #20210305
            order_number = current_date + str(data.id)
            data.order_number = order_number
            data.save()
            order = Order.objects.get(user=current_user, is_ordered=False, order_number=order_number)
            context = {
                'order': order,
                'cart_items': cart_items,
                'total': total,
                'tax': tax,
                'grand_total': grand_total,
            }
            return render(request, 'orders/payments.html', context)
            
        
        else:
            return redirect('checkout')
            
    
def order_complete(request):
    order_number = request.GET.get('order_number')
    transID = request.GET.get('payment_id')

    try:
        order = Order.objects.get(order_number=order_number, is_ordered=True)
        ordered_products = OrderProduct.objects.filter(order_id=order.id)

        subtotal = 0
        for i in ordered_products:
            subtotal += i.product_price * i.quantity

        payment = Payment.objects.get(payment_id=transID)

        context = {
            'order': order,
            'ordered_products': ordered_products,
            'order_number': order.order_number,
            'transID': payment.payment_id,
            'payment': payment,
            'subtotal': subtotal,
        }
        return render(request, 'orders/order_complete.html', context)
    except (Payment.DoesNotExist, Order.DoesNotExist):
        return redirect('home')


def analytics(request):
    user = request.user
    qs_order_product = OrderProduct.objects.all()
    qs_orders = Order.objects.all()
    
    # Count unique users who ordered from this app
    count_users = Order.objects.all().values('user_id').distinct().count()
    print(count_users) 

    red_jeans_count = 0
    blue_jeans_count = 0
    green_jeans_count = 0
    total_money_from_orders = 0
    
    red_jeans_query_set = OrderProduct.objects.filter(variations__variation_value='Red').all()
    for i in red_jeans_query_set.values():
        # print(i)
        red_jeans_count += i['quantity']
        
    blue_jeans_query_set = OrderProduct.objects.filter(variations__variation_value='Blue').all()
    for i in blue_jeans_query_set.values():
        # print(i)
        blue_jeans_count += i['quantity']
        
    green_jeans_query_set = OrderProduct.objects.filter(variations__variation_value='Green').all()
    for i in green_jeans_query_set.values():
        # print(i)
        green_jeans_count += i['quantity']
    
    # red_jeans = OrderProduct.objects.filter(variations__variation_value='Red').count()
    # blue_jeans = OrderProduct.objects.filter(variations__variation_value='Blue').count()
    # green_jeans = OrderProduct.objects.filter(variations__variation_value='Green').count()
    total_money_from_orders_dict = Order.objects.all().aggregate(Sum("order_total"))
    total_money_from_orders = total_money_from_orders_dict['order_total__sum']
        
    print('red_jeans_count ', red_jeans_count)
    print('blue_jeans_count ', blue_jeans_count)
    print('green_jeans_count ', green_jeans_count)
    
    total_jeans_count = red_jeans_count + blue_jeans_count + green_jeans_count
    
    # filtering the  orders by the date   
    
    # Last 3 days orders 
    last_3_days_date = datetime.datetime.now() - datetime.timedelta(days=3)
    # print(last_3_days_date)
    qs_by_last_3_days = Order.objects.all().filter(updated_at__day__gte=last_3_days_date.day)
    

    
    if request.method == 'POST':
            days = request.POST.get('days')
            print("DAYS are ..................... ", days)
    days = int(days)
    # filtering the  orders by the date  dynamically
    start_date = datetime.datetime.now() - datetime.timedelta(days=days)
    end_date = datetime.datetime.now() - datetime.timedelta(days=0)
    qs_by_custom_range = Order.objects.by_range(start_date=start_date, end_date=end_date)
    print(qs_by_custom_range)
    # print("The total orders over last " + str(days) + " days are ", qs_by_custom_range.count())
    
    number_of_orders = qs_by_custom_range.count()
    
    custom_order_total = 0
    city_orders_track_dict = {}
    for i in qs_by_custom_range:
        custom_order_total += i.order_total
        if i.city in city_orders_track_dict:
            city_orders_track_dict[i.city] += 1
        else:
            city_orders_track_dict[i.city] = 1
            
    print("CITY ORDERS TRACK ", city_orders_track_dict)
    
    context = {
            'user': user,
            'qs_order_product': qs_order_product,
            'qs_orders': qs_orders,
            'count_users' : count_users,
            'red_jeans_count' : red_jeans_count,
            'blue_jeans_count' : blue_jeans_count,
            'green_jeans_count' : green_jeans_count,
            'total_jeans_count' : total_jeans_count,
            'total_money_from_orders': total_money_from_orders,
            'number_of_orders' : number_of_orders,
            'days' : days,
            'custom_order_total' : custom_order_total,
            'city_orders_track_dict' : city_orders_track_dict,
            
        }
    return render(request, 'orders/analytics.html', context)