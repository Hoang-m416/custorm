{
    "name": "FORHER - Thu hồi tài sản (Offboarding)",
    "summary": "Quy trình thu hồi tài sản khi nhân viên nghỉ việc",
    "version": "18.0.1.0",
    "category": "Human Resources",
    "author": "FORHER BPMN",
    "depends": [
        "hr",
        "hr_contract",
        "mail",
        "maintenance",  # dùng maintenance.equipment để lấy tài sản đã giao NV
        "forher_contract",
        "forher_hr_employee",
        "forher_company_overview",
    ],
    "data": [
        "security/ir.model.access.csv",
        "data/sequence.xml",
        "data/mail_template.xml",
        "report/offboarding_assets_report.xml",
        "report/offboarding_report_templates.xml",
        "report/offboarding_report_actions.xml",
        "views/menus.xml",
        "views/offboarding_request_views.xml",
        "views/hr_employee_views_inherit.xml",
        "report/report.xml",
        "data/demo_data.xml",  # <-- THÊM VÀO ĐÂY để nạp ngay khi cài module
    ],
    
    "application": True,
    "installable": True,
    "license": "LGPL-3",
    "icon": "/offboarding_assets/static/description/icon.png",
}
