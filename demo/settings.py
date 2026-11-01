import os



ENVIRONMENT = os.getenv('ENVIRONMENT', 'development')



DEBUG = os.getenv('DEBUG', 'true').strip().lower() in {'1', 'true', 'yes', 'on'}

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

SECRET_KEY = os.getenv('SECRET_KEY', 'django-insecure-local-development-key-change-before-deploy')

ALLOWED_HOSTS = [host.strip() for host in os.getenv('ALLOWED_HOSTS', '*').split(',') if host.strip()]



INSTALLED_APPS = [

    'jazzmin',

    'django.contrib.admin',

    'django.contrib.auth',

    'django.contrib.contenttypes',

    'django.contrib.sessions',

    'django.contrib.messages',

    'django.contrib.staticfiles',

    'django.contrib.sites',



    # Allauth

    'allauth',

    'allauth.account',

    'allauth.socialaccount',

    'allauth.socialaccount.providers.google',



    # 3rd party

    'crispy_forms',

    'crispy_bootstrap4',

    'django_countries',



    # Local apps

    'core.apps.CoreConfig'

]



MIDDLEWARE = [

    'django.middleware.security.SecurityMiddleware',

    'whitenoise.middleware.WhiteNoiseMiddleware',

    'django.contrib.sessions.middleware.SessionMiddleware',


    'django.middleware.common.CommonMiddleware',

    'django.middleware.csrf.CsrfViewMiddleware',

    'django.contrib.auth.middleware.AuthenticationMiddleware',

    'django.contrib.messages.middleware.MessageMiddleware',

    'django.middleware.clickjacking.XFrameOptionsMiddleware',

    'allauth.account.middleware.AccountMiddleware',

]



ROOT_URLCONF = 'demo.urls'



TEMPLATES = [

    {

        'BACKEND': 'django.template.backends.django.DjangoTemplates',

        'DIRS': [os.path.join(BASE_DIR, 'templates')],

        'APP_DIRS': True,

        'OPTIONS': {

            'context_processors': [

                'django.template.context_processors.debug',

                'django.template.context_processors.request',  # Required by allauth

                'django.contrib.auth.context_processors.auth',

                'django.contrib.messages.context_processors.messages',
                'core.context_processors.shopping_cart',

            ],

        },

    },

]



WSGI_APPLICATION = 'demo.wsgi.application'



if os.getenv('DB_ENGINE', 'sqlite').strip().lower() in {'postgres', 'postgresql'}:
    DATABASES = {
        'default': {
            'ENGINE': 'django.db.backends.postgresql',
            'NAME': os.getenv('POSTGRES_DB', 'nhang_shop'),
            'USER': os.getenv('POSTGRES_USER', 'nhang_shop'),
            'PASSWORD': os.getenv('POSTGRES_PASSWORD', ''),
            'HOST': os.getenv('POSTGRES_HOST', 'db'),
            'PORT': os.getenv('POSTGRES_PORT', '5432'),
            'CONN_MAX_AGE': 60,
            'CONN_HEALTH_CHECKS': True,
        }
    }
else:
    DATABASES = {
        'default': {
            'ENGINE': 'django.db.backends.sqlite3',
            'NAME': os.getenv('SQLITE_DB_NAME', os.path.join(BASE_DIR, 'db.sqlite3')),
        }
    }



AUTH_PASSWORD_VALIDATORS = [

    {

        'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator',

    },

    {

        'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator',

    },

    {

        'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator',

    },

    {

        'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator',

    },

]



LANGUAGE_CODE = 'en-us'

TIME_ZONE = 'UTC'

USE_I18N = True

USE_L10N = True

USE_TZ = True



STATIC_URL = '/static/'

STATICFILES_DIRS = [

    os.path.join(BASE_DIR, 'static_in_env'),
    os.path.join(BASE_DIR, 'static')

]

STATIC_ROOT = os.path.join(BASE_DIR, 'staticfiles')



MEDIA_URL = '/media/'

MEDIA_ROOT = os.path.join(BASE_DIR, 'media_root')



# Production settings

if ENVIRONMENT == 'production':

    DEBUG = False

    if not os.getenv('SECRET_KEY') or SECRET_KEY.startswith('django-insecure-local') or SECRET_KEY == 'replace-with-a-random-secret':
        raise RuntimeError('SECRET_KEY must be set when ENVIRONMENT=production.')
    if ALLOWED_HOSTS == ['*']:
        raise RuntimeError('Set ALLOWED_HOSTS explicitly when ENVIRONMENT=production.')

    SESSION_COOKIE_SECURE = True

    SECURE_BROWSER_XSS_FILTER = True

    SECURE_CONTENT_TYPE_NOSNIFF = True

    SECURE_HSTS_INCLUDE_SUBDOMAINS = True

    SECURE_HSTS_SECONDS = 31536000

    SECURE_REDIRECT_EXEMPT = []

    SECURE_SSL_REDIRECT = os.getenv('SECURE_SSL_REDIRECT', 'true').strip().lower() in {'1', 'true', 'yes', 'on'}

    SECURE_PROXY_SSL_HEADER = ('HTTP_X_FORWARDED_PROTO', 'https')



# Authentication

AUTHENTICATION_BACKENDS = (

    'django.contrib.auth.backends.ModelBackend',

    'allauth.account.auth_backends.AuthenticationBackend'

)



SITE_ID = 1

LOGIN_REDIRECT_URL = '/'



# django-allauth specific

ACCOUNT_EMAIL_VERIFICATION = 'optional'  # Đặt thành 'mandatory' nếu muốn bắt buộc xác nhận email

ACCOUNT_LOGIN_METHODS = {'username', 'email'}

ACCOUNT_SIGNUP_FIELDS = ['email*', 'username*', 'password1*', 'password2*']



# Social account providers

SOCIALACCOUNT_PROVIDERS = {

    'google': {

        'APP': {

            'client_id': '123',

            'secret': '456',

            'key': '666'

        }

    }

}



# CRISPY FORMS

CRISPY_TEMPLATE_PACK = 'bootstrap4'



# Stripe keys (fake for testing)

STRIPE_PUBLIC_KEY = 'pk_test_lX3r6OMjOU2yzFsNSHq6belT00EY82kZmH'



STRIPE_SECRET_KEY = os.getenv("STRIPE_SECRET_KEY")

EMAIL_BACKEND = os.getenv(
    'EMAIL_BACKEND',
    'django.core.mail.backends.console.EmailBackend' if DEBUG else 'django.core.mail.backends.smtp.EmailBackend',
)
EMAIL_HOST = os.getenv('EMAIL_HOST', '')
EMAIL_PORT = int(os.getenv('EMAIL_PORT', '587'))
EMAIL_HOST_USER = os.getenv('EMAIL_HOST_USER', '')
EMAIL_HOST_PASSWORD = os.getenv('EMAIL_HOST_PASSWORD', '')
EMAIL_USE_TLS = os.getenv('EMAIL_USE_TLS', 'true').strip().lower() in {'1', 'true', 'yes', 'on'}
DEFAULT_FROM_EMAIL = os.getenv('DEFAULT_FROM_EMAIL', 'Nhang Shop <no-reply@localhost>')
SITE_URL = os.getenv('SITE_URL', 'http://127.0.0.1:8000')





# ✅ Email backend for development

JAZZMIN_SETTINGS = {
    'site_title': 'Nhang Shop Admin',
    'site_header': 'Nhang Shop',
    'site_brand': 'Nhang Shop',
    'welcome_sign': 'Welcome to Nhang Shop Admin',
    'copyright': 'Nhang Shop',
    'show_ui_builder': False,
    'custom_css': 'css/nhang_admin.css',
    'icons': {
        'auth.Group': 'fas fa-users',
        'auth.User': 'fas fa-user',
        'core.Item': 'fas fa-box-open',
        'core.ItemVariant': 'fas fa-tags',
        'core.Category': 'fas fa-layer-group',
        'core.Order': 'fas fa-shopping-bag',
        'core.Payment': 'fas fa-credit-card',
        'core.Coupon': 'fas fa-ticket-alt',
        'core.Refund': 'fas fa-undo',
        'core.Slide': 'fas fa-images',
        'core.StockReceipt': 'fas fa-boxes',
        'core.StockMovement': 'fas fa-exchange-alt',
        'core.Supplier': 'fas fa-truck',
        'core.Review': 'fas fa-star',
    },
}

JAZZMIN_UI_TWEAKS = {
    "navbar": "navbar-white navbar-light",
    "theme": "default",
    "sidebar": "sidebar-light-success",
    "sidebar_nav_child_indent": True,
    "sidebar_nav_compact_style": True,
    "sidebar_nav_legacy_style": False,
    "sidebar_nav_flat_style": False,
    "theme_color": "success",
    "dark_mode_theme": None,
    "button_classes": {
        "primary": "btn-success",
        "secondary": "btn-outline-secondary",
        "info": "btn-outline-info",
        "warning": "btn-warning",
        "danger": "btn-danger",
        "success": "btn-success"
    }
}

