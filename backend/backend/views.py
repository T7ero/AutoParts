from django.http import JsonResponse

def home(request):
    return JsonResponse({
        'message': 'Добро пожаловать в API системы управления автозапчастями',
        'status': 'active'
    }) 