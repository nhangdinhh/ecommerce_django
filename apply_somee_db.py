import sys
with open('demo/settings.py', 'r', encoding='utf-8') as f:
    content = f.read()

old = '''DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": os.path.join(BASE_DIR, 'db.sqlite3')
    }
}'''
new = '''DATABASES = {
    'default': {
        'ENGINE': 'mssql',
        'NAME': 'django_db',
        'USER': 'nhangdinh_SQLLogin_1',
        'PASSWORD': 'l1bh784zm2',
        'HOST': 'django_db.mssql.somee.com',
        'PORT': '',
        'OPTIONS': {
            'driver': 'ODBC Driver 17 for SQL Server',
            'isolation_level': 'READ UNCOMMITTED',
        },
    }
}'''
content = content.replace(old, new)
with open('demo/settings.py', 'w', encoding='utf-8') as f:
    f.write(content)
