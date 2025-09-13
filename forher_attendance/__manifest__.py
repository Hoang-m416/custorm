{
    'name': 'Forher Attendance',
    'version': '18.0.1.0.0',
    'summary': 'Hệ thống chấm công Forher',
    'description': '''
    Module chấm công tích hợp Forher:
    - Kế thừa hr_attendance của Odoo
    - Thêm trạng thái duyệt
    - Tích hợp chi nhánh
    ''',
    'author': 'Forher IT',
    'category': 'Human Resources',
    'depends': [
        'hr_attendance',
        'hr',
        'base','forher_contract','forher_company_overview',
        'resource',
    ],
    'data': [
        'security/ir.model.access.csv',
        'views/hr_attendance_views.xml',
        'views/attendance_dashboard_views.xml',
        'views/manager_overview_views.xml',
        'views/menu.xml',
    ],
    'installable': True,
    'application': True,
}
