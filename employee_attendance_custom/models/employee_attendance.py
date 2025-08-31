from odoo import models, fields, api, _
from odoo.exceptions import UserError, ValidationError
from datetime import date

# ================= CHẤM CÔNG =================
class EmployeeAttendanceCustom(models.Model):
    _name = "employee.attendance.custom"
    _description = "Chấm công nhân sự"
    _inherit = ['mail.thread', 'mail.activity.mixin']

    employee_id = fields.Many2one('hr.employee', string="Nhân sự", required=True, tracking=True)
    date = fields.Date(string="Ngày công", default=lambda self: date.today(), tracking=True)
    check_in = fields.Datetime(string="Giờ vào", tracking=True)
    check_out = fields.Datetime(string="Giờ ra", tracking=True)
    work_type = fields.Selection([
        ('normal', 'Công bình thường'),
        ('teaching', 'Hợp đồng giảng dạy'),
        ('contract', 'Hợp đồng khoán')
    ], string="Loại công", default='normal', tracking=True)
    work_hours = fields.Float(string="Số giờ làm việc", compute="_compute_work_hours", store=True)
    work_hours_display = fields.Char(string="Giờ làm việc (hh:mm)", compute="_compute_work_hours_display")
    overtime = fields.Float(string="OT (giờ)", tracking=True)
    leave_days = fields.Float(string="Ngày phép", default=0.0, tracking=True)
    note = fields.Text(string="Giải trình")

    status = fields.Selection([
        ('draft', 'Chưa check in'),
        ('confirmed', 'Đã check in'),
        ('approved', 'Đã check out')
    ], string="Trạng thái", default='draft', tracking=True)

    approval_status = fields.Selection([
        ('waiting', 'Chờ duyệt'),
        ('accepted', 'Chấp nhận OT'),
        ('refused', 'Từ chối OT')
    ], string="Duyệt OT", default='waiting', tracking=True)

    # ================== COMPUTE ==================
    @api.depends('check_in', 'check_out')
    def _compute_work_hours(self):
        for rec in self:
            if rec.check_in and rec.check_out and rec.check_out >= rec.check_in:
                diff = rec.check_out - rec.check_in
                rec.work_hours = round(diff.total_seconds() / 3600, 2)
            else:
                rec.work_hours = 0.0

    @api.depends('check_in', 'check_out')
    def _compute_work_hours_display(self):
        for rec in self:
            if rec.check_in and rec.check_out and rec.check_out >= rec.check_in:
                diff = rec.check_out - rec.check_in
                hours, remainder = divmod(int(diff.total_seconds()), 3600)
                minutes = remainder // 60
                rec.work_hours_display = f"{hours}:{minutes:02d}"
            else:
                rec.work_hours_display = "0:00"

    # ================== ACTIONS ==================
    def _action_open_check_wizard(self, check_type):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _("Chọn thời gian"),
            'res_model': 'attendance.check.wizard',
            'view_mode': 'form',
            'target': 'new',
            'context': {
                'default_attendance_id': self.id,
                'default_employee_id': self.employee_id.id,
                'default_check_type': check_type,
                'default_check_datetime': fields.Datetime.now(),
            }
        }

    def action_open_checkin_wizard(self):
        return self._action_open_check_wizard('in')

    def action_open_checkout_wizard(self):
        return self._action_open_check_wizard('out')

    def action_accept_overtime(self):
        self.write({'approval_status': 'accepted'})

    def action_refuse_overtime(self):
        self.write({'approval_status': 'refused'})


# ================= WIZARD =================
class AttendanceCheckWizard(models.TransientModel):
    _name = "attendance.check.wizard"
    _description = "Wizard chọn thời gian Check In/Out"

    attendance_id = fields.Many2one('employee.attendance.custom', string="Bản ghi chấm công", required=True)
    employee_id = fields.Many2one('hr.employee', string="Nhân sự", required=True)
    check_type = fields.Selection([('in','Check In'),('out','Check Out')], string="Loại", required=True)
    check_datetime = fields.Datetime(string="Thời gian", required=True,
                                     default=lambda self: fields.Datetime.now())
    note = fields.Char(string="Ghi chú")

    def action_confirm(self):
        self.ensure_one()
        rec = self.attendance_id
        now = fields.Datetime.now()
        dt = self.check_datetime or now

        if self.check_type == 'in':
            if rec.check_in:
                raise UserError("Bản ghi đã có Check In.")
            rec.write({
                'check_in': dt,
                'status': 'confirmed',
                'note': (rec.note or '') + (f"\n[Check In wizard] {self.note}" if self.note else '')
            })
        else:
            if not rec.check_in:
                raise UserError("Chưa có Check In để Check Out.")
            if rec.check_out:
                raise UserError("Bản ghi đã có Check Out.")
            if dt < rec.check_in:
                raise ValidationError("Thời điểm Check Out phải >= Check In.")
            rec.write({
                'check_out': dt,
                'status': 'approved',
                'note': (rec.note or '') + (f"\n[Check Out wizard] {self.note}" if self.note else '')
            })
        return {'type': 'ir.actions.act_window_close'}


# ================= NGHỈ PHÉP =================
class EmployeeLeaveRequest(models.Model):
    _name = "employee.leave.request"
    _description = "Đơn nghỉ phép / Giải trình"
    _inherit = ['mail.thread', 'mail.activity.mixin']

    employee_id = fields.Many2one("hr.employee", string="Nhân sự", required=True, tracking=True)
    start_date = fields.Date(string="Ngày bắt đầu", required=True, tracking=True)
    end_date = fields.Date(string="Ngày kết thúc", required=True, tracking=True)
    leave_days = fields.Float(string="Số ngày nghỉ", compute="_compute_leave_days", store=True)
    reason = fields.Text(string="Lý do nghỉ", tracking=True)
    status = fields.Selection([
        ("draft", "Nháp"),
        ("manager_approved", "Trưởng đơn vị duyệt"),
        ("hr_approved", "P.TC-HC/Hiệu trưởng duyệt"),
        ("done", "Hoàn thành"),
        ("refused", "Từ chối"),
    ], string="Trạng thái", default="draft", tracking=True)

    @api.depends("start_date", "end_date")
    def _compute_leave_days(self):
        for rec in self:
            if rec.start_date and rec.end_date and rec.end_date >= rec.start_date:
                rec.leave_days = (rec.end_date - rec.start_date).days + 1
            else:
                rec.leave_days = 0

    # ================== ACTIONS ==================
    def action_manager_approve(self):
        self.write({"status": "manager_approved"})

    def action_hr_approve(self):
        self.write({"status": "hr_approved"})

    def action_done(self):
        self.write({"status": "done"})

    def action_refuse(self):
        self.write({"status": "refused"})
