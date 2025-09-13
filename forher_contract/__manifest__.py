{
    'name': 'Forher Contract',
    'version': '18.0.0.0.1',
    'summary': "Quản lý hợp đồng cho công ty Forher",
    'category': 'Human Resources',
    'author': 'Forher IT',
    'depends': [
        "hr",
        "hr_contract",
        "mail",
    
    ],
    'data': [
        'security/ir.model.access.csv',
        'security/groups.xml',
        'security/ir_rule.xml',
        'data/forher_calendar_fulltime.xml',
        'data/forher_attendance_catoi.xml',
        'data/forher_attendance_casang.xml',
        'data/ir_sequence_data.xml',
        'data/mail_template.xml',
        'data/ir_cron.xml',
        'views/forher_hr_contract.xml',
        'views/forher_hr_contract_report_views.xml',
        'views/menu.xml',
    ],
    'installable': True,
    'application': True,
}
