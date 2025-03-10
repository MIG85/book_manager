from django.shortcuts import render, redirect
from django.contrib.auth import login, logout
from django.views import View
from .forms import LoginForm, RegisterForm

class LoginView(View):
    def get(self, request):
        form = LoginForm()
        return render(request, 'users/login.html', {'form': form})

    def post(self, request):
        form = LoginForm(data=request.POST)
        if form.is_valid():
            user = form.get_user()
            login(request, user)
            return redirect('books:list')
        return render(request, 'users/login.html', {'form': form})

class RegisterView(View):
    def get(self, request):
        form = RegisterForm()
        return render(request, 'users/register.html', {'form': form})

    def post(self, request):
        form = RegisterForm(request.POST)
        if form.is_valid():
            user = form.save()
            login(request, user)
            return redirect('books:list')
        return render(request, 'users/register.html', {'form': form})

def logout_view(request):
    logout(request)
    return redirect('home')