"""
Run with: python manage.py shell < create_test_users.py
Creates operator (pk=1) and tourist (pk=2) for fixture loading.
"""
from apps.users.models import User

# Operator — pk=1
if not User.objects.filter(pk=1).exists():
    u = User(
        pk=1,
        email='operator@waybound.com',
        first_name='Sandro',
        last_name='Beridze',
        role='operator',
        is_staff=True,
        is_superuser=True,
    )
    u.set_password('Waybound2026!')
    u.save()
    print(f"Operator created: {u.email} pk={u.pk}")
else:
    print(f"Operator pk=1 already exists")

# Tourist — pk=2
if not User.objects.filter(pk=2).exists():
    u = User(
        pk=2,
        email='test@waybound.com',
        first_name='Alex',
        last_name='Petrov',
        role='tourist',
    )
    u.set_password('Waybound2026!')
    u.save()
    print(f"Tourist created: {u.email} pk={u.pk}")
else:
    print(f"Tourist pk=2 already exists")

print("Done. Now run:")
print("  python manage.py loaddata apps/tours/fixtures/initial_tours.json")
print("  python manage.py loaddata apps/bookings/fixtures/dashboard_test.json")
