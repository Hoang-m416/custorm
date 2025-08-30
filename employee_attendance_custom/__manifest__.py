{
    "name": "Employee Attendance Custom",
    "version": "1.0",
    "summary": "Module chấm công mở rộng, kế thừa HR Attendance",
    "sequence": 10,
    "description": "Module quản lý chấm công, ngày phép, OT, hỗ trợ kế thừa và mở rộng",
    "category": "Human Resources",
    "author": "Your Name",
    "website": "https://yourcompany.com",
    "depends": ["base", "hr",],
    "data": [
        "security/ir.model.access.csv",
        "views/employee_attendance_views.xml",
    ],
    "installable": True,
    "application": True,
    "auto_install": False,
}
