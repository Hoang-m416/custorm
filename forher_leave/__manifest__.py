{
    "name": "Forher Leave Management",
    "version": "1.0",
    "summary": "Quản lý nghỉ phép nhân viên",
    "author": "Forher",
    "depends": ["base", "hr", "mail",'forher_company_overview'],
    "data": [
        "security/ir.model.access.csv",
        "views/leave_type_views.xml",
        "views/holiday_views.xml",
        "views/leave_request_views.xml",
        "views/menu_views.xml",
        "data/holiday_data.xml",
    ],
    "application": True,
}
