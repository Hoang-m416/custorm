from odoo import models, fields, api
from datetime import datetime, date

# ================= CHẤM CÔNG =================
class EmployeeAttendanceCustom(models.Model):
    _name = "employee.attendance.custom"
    _description = "Chấm công nhân sự"
    _inherit = ['mail.thread', 'mail.activity.mixin']

    employee_id = fields.Many2one('hr.employee', string="Nhân sự", required=True)
    date = fields.Date(string="Ngày công", default=lambda self: date.today())
    check_in = fields.Datetime(string="Giờ vào")
    check_out = fields.Datetime(string="Giờ ra")
    work_type = fields.Selection([
        ('normal', 'Công bình thường'),
        ('teaching', 'Hợp đồng giảng dạy'),
        ('contract', 'Hợp đồng khoán')
    ], string="Loại công", default='normal')
    work_hours = fields.Float(string="Số giờ làm việc", compute="_compute_work_hours", store=True)
    work_hours_display = fields.Char(string="Giờ làm việc (hh:mm)", compute="_compute_work_hours_display")
    overtime = fields.Float(string="OT (giờ)")
    leave_days = fields.Float(string="Ngày phép", default=0.0)
    note = fields.Text(string="Giải trình")
    status = fields.Selection([
        ('confirmed', 'Đã check in'),
        ('approved', 'Đã check out')
    ], string="Trạng thái", default='confirmed', tracking=True)

    @api.depends('check_in', 'check_out')
    def _compute_work_hours(self):
        for rec in self:
            if rec.check_in and rec.check_out:
                diff = rec.check_out - rec.check_in
                total_minutes = diff.total_seconds() / 60
                rec.work_hours = round(total_minutes / 60, 2)
            else:
                rec.work_hours = 0.0

    @api.depends('check_in', 'check_out')
    def _compute_work_hours_display(self):
        for rec in self:
            if rec.check_in and rec.check_out:
                diff = rec.check_out - rec.check_in
                hours, remainder = divmod(int(diff.total_seconds()), 3600)
                minutes = remainder // 60
                rec.work_hours_display = f"{hours}:{minutes:02d}"
            else:
                rec.work_hours_display = "0:00"

    def action_check_in(self):
        for rec in self:
            rec.check_in = datetime.now()
            rec.status = 'confirmed'

    def action_check_out(self):
        for rec in self:
            rec.check_out = datetime.now()
            rec.status = 'approved'

# ================= NGHỈ PHÉP / GIẢI TRÌNH =================
class EmployeeLeaveRequest(models.Model):
    _name = "employee.leave.request"
    _description = "Đơn xin nghỉ phép / Giải trình"
    _inherit = ['mail.thread', 'mail.activity.mixin']

    employee_id = fields.Many2one('hr.employee', string="Nhân sự", required=True)
    start_date = fields.Date(string="Ngày bắt đầu")
    end_date = fields.Date(string="Ngày kết thúc")
    leave_days = fields.Float(string="Số ngày", compute="_compute_leave_days", store=True)
    reason = fields.Text(string="Lý do / Giải trình")
    status = fields.Selection([
        ('draft', 'Nháp'),
        ('manager_approved', 'Trưởng đơn vị duyệt'),
        ('hr_approved', 'P.TC-HC/Hiệu trưởng duyệt'),
        ('done', 'Được duyệt'),
        ('refused', 'Từ chối')
    ], string="Trạng thái", default='draft', tracking=True)

    @api.depends('start_date', 'end_date')
    def _compute_leave_days(self):
        for rec in self:
            if rec.start_date and rec.end_date:
                rec.leave_days = (rec.end_date - rec.start_date).days + 1
            else:
                rec.leave_days = 0

    # Các hành động phê duyệt / từ chối
    def action_manager_approve(self):
        for rec in self:
            rec.status = 'manager_approved'

    def action_hr_approve(self):
        for rec in self:
            rec.status = 'hr_approved'

    def action_done(self):
        for rec in self:
            rec.status = 'done'

    def action_refuse(self):
        for rec in self:
            rec.status = 'refused'
