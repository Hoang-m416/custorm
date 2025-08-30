{
    'name': 'Forher HR Employee',
    'version': '1.0',
    'category': 'Human Resources',
    'summary': 'Mở rộng nhân viên, chuẩn hóa hồ sơ, phân quyền theo module Forher Company Overview',
    'depends': ['base', 'hr', 'forher_company_overview', 'mail'],
    'data': [
        'security/hr_employee_security.xml',
        'security/ir.model.access.csv',
        'views/forher_branch_views.xml',
        'views/employee_type_views.xml',
        'views/hr_employee_menus.xml',
        'views/hr_employee_views.xml',
    ],
    'installable': True,
    'application': False,
}