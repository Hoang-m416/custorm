{
    'name': 'Custom User Password',
    'version': '1.0',
    'summary': 'Thêm ô nhập mật khẩu khi tạo User, kèm kiểm tra độ mạnh',
    'author': 'Bạn',
    'depends': ['base', 'password_security'],  # password_security giúp enforce chính sách
    'data': [
        'views/res_users_view.xml',
    ],
    'installable': True,
    'application': False,
}

