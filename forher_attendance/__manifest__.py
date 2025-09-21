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
        'web',  # Thêm để hỗ trợ kiosk
        'hr_attendance',
        'hr',
        'base',
        'forher_contract',
        'forher_company_overview',
        'resource',
    ],
    'data': [
        'security/attendance_security.xml',
        'security/ir.model.access.csv',
        'data/kiosk_config_data.xml',
        'data/forher_attendance_type_data.xml',
        # 'data/forher_calendar_data.xml',
        # 'data/forher_calendar_fulltime.xml',
        # 'data/forher_attendance_catoi.xml',
        # 'data/forher_attendance_casang.xml',
        'views/hr_employee_views.xml',
        'views/hr_attendance_views.xml',
        'views/attendance_dashboard_views.xml',
        'views/manager_overview_views.xml',
        'views/kiosk_assets.xml',      # <-- ĐỂ TRƯỚC
        'views/kiosk_templates.xml',   # <-- ĐỂ SAU
        'views/hr_attendance_manager_views.xml',
        'views/forher_shift_views.xml',
        'views/menu.xml',
    ],
    'installable': True,
    'application': True,
}
