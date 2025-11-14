from django.test import TestCase
from django.core.management import call_command
from django.contrib.auth import get_user_model
from rest_framework.test import APIClient
from rest_framework.authtoken.models import Token
from app.models import Role, UserRole


class RBACMatrixTests(TestCase):
    def setUp(self):
        call_command('setup_rbac')
        self.User = get_user_model()
        # Create users
        self.chief = self.User.objects.create_user(username='chief', password='pass')
        self.accountant = self.User.objects.create_user(username='accountant', password='pass')
        self.auditor = self.User.objects.create_user(username='auditor', password='pass')
        self.clerk = self.User.objects.create_user(username='clerk', password='pass')

        # Assign roles
        chief_role = Role.objects.get(name='Chief Officer')
        acct_role = Role.objects.get(name='Accountant Officer')
        auditor_role = Role.objects.get(name='Auditor')
        clerk_role = Role.objects.get(name='Clerk')
        UserRole.objects.create(user=self.chief, role=chief_role, is_active=True)
        UserRole.objects.create(user=self.accountant, role=acct_role, is_active=True)
        UserRole.objects.create(user=self.auditor, role=auditor_role, is_active=True)
        UserRole.objects.create(user=self.clerk, role=clerk_role, is_active=True)

        # Tokens and clients
        def client_for(user):
            tok, _ = Token.objects.get_or_create(user=user)
            c = APIClient()
            c.credentials(HTTP_AUTHORIZATION=f'Token {tok.key}')
            return c

        self.chief_client = client_for(self.chief)
        self.acct_client = client_for(self.accountant)
        self.auditor_client = client_for(self.auditor)
        self.clerk_client = client_for(self.clerk)

    def test_clerk_can_view_reports_but_not_add_transactions(self):
        # Reports
        resp = self.clerk_client.get('/api/reports/', {'type': 'profit-loss'})
        self.assertEqual(resp.status_code, 200)
        # Add transaction forbidden
        payload = {
            'tx_type': 'credit',
            'amount': 100,
            'account': 'Credit',
        }
        resp = self.clerk_client.post('/api/transactions/', payload, format='json')
        self.assertEqual(resp.status_code, 403)

    def test_accountant_can_add_and_delete_transactions(self):
        # Add
        payload = {'tx_type': 'credit', 'amount': 50, 'account': 'Credit'}
        resp = self.acct_client.post('/api/transactions/', payload, format='json')
        self.assertEqual(resp.status_code, 201)
        tx_id = resp.json().get('transaction_id')
        # Delete
        resp = self.acct_client.delete(f'/api/transactions/{tx_id}/')
        self.assertIn(resp.status_code, (200, 204))

    def test_accountant_cannot_delete_bank_accounts(self):
        # Create bank via chief (has full rights)
        payload = {'account_name': 'Test', 'account_no': '123456789', 'ifsc': 'ABCD0123456', 'bank_name': 'SBI', 'status': 'active'}
        resp = self.chief_client.post('/api/bank-accounts/', payload, format='json')
        self.assertEqual(resp.status_code, 201)
        bank_id = resp.json().get('account_id')
        # Accountant cannot delete
        resp = self.acct_client.delete(f'/api/bank-accounts/{bank_id}/')
        self.assertEqual(resp.status_code, 403)

    def test_auditor_can_add_edit_contractor_but_not_delete(self):
        # Add contractor
        payload = {
            'contractor_name': 'C1', 'contractor_address': 'Addr', 'contractor_contact_no': '9999999999',
            'contractor_pan': 'ABCDE1234F', 'contractor_tan': 'ABCD12345B', 'contractor_gst': '22ABCDE1234F1Z5',
            'contractor_bank_ac': '123456789', 'contractor_ifsc': 'ABCD0123456', 'contractor_bank': 'SBI', 'status': 'active'
        }
        resp = self.auditor_client.post('/api/contractors/', payload, format='json')
        self.assertEqual(resp.status_code, 201)
        cid = resp.json().get('contractor_id')
        # Edit
        resp = self.auditor_client.patch(f'/api/contractors/{cid}/', {'remark': 'ok'}, format='json')
        self.assertEqual(resp.status_code, 200)
        # Delete forbidden
        resp = self.auditor_client.delete(f'/api/contractors/{cid}/')
        self.assertEqual(resp.status_code, 403)

    def test_backup_restore_permissions(self):
        # Accountant can create backup
        resp = self.acct_client.post('/api/backup/', {'action': 'backup'}, format='json')
        self.assertEqual(resp.status_code, 200)
        # Accountant cannot restore
        resp = self.acct_client.post('/api/backup/', {'action': 'restore', 'file': 'nonexistent.json'}, format='json')
        self.assertEqual(resp.status_code, 403)
        # Chief can restore (even with invalid file gets 400 or handled)
        resp = self.chief_client.post('/api/backup/', {'action': 'restore', 'file': 'nonexistent.json'}, format='json')
        self.assertIn(resp.status_code, (200, 400))

    def test_me_permissions_fallback_to_user_role_choice(self):
        User = get_user_model()
        # Create a user with role=3 (Auditor) but DO NOT create UserRole mapping
        u = User.objects.create_user(username='auditor_nour', password='pass', role=3)
        tok, _ = Token.objects.get_or_create(user=u)
        c = APIClient()
        c.credentials(HTTP_AUTHORIZATION=f'Token {tok.key}')
        resp = c.get('/api/me/permissions/')
        self.assertEqual(resp.status_code, 200)
        perms = set(resp.json().get('permissions') or [])
        # Auditor expected key permissions should be present via fallback
        self.assertIn('view_contractors', perms)
        self.assertIn('add_contractors', perms)
        self.assertIn('edit_contractors', perms)
        self.assertIn('view_banks', perms)
        self.assertIn('view_transactions', perms)

    def test_userrole_auto_created_on_user_add(self):
        payload = {"username": "newauditor", "password": "pass", "role": 3, "status": "active"}
        resp = self.chief_client.post('/api/users/', payload, format='json')
        self.assertEqual(resp.status_code, 201)
        User = get_user_model()
        u = User.objects.get(username='newauditor')
        role = Role.objects.get(name='Auditor')
        self.assertTrue(UserRole.objects.filter(user=u, role=role, is_active=True).exists())
        tok, _ = Token.objects.get_or_create(user=u)
        c = APIClient()
        c.credentials(HTTP_AUTHORIZATION=f'Token {tok.key}')
        resp = c.get('/api/transactions/')
        self.assertEqual(resp.status_code, 200)
