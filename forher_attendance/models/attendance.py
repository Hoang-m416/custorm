# file: models/forher_attendance.py
from odoo import api, fields, models, _, tools
from odoo.exceptions import ValidationError, UserError
from datetime import datetime, timedelta, date
import pytz
from odoo.http import request

# -------------------------
# Attendance Type (loại công)
# -------------------------
class ForHerAttendanceType(models.Model):
    _name = 'forher.attendance.type'
    _description = 'Loại công ForHer'
    _order = 'sequence, id'

    name = fields.Char('Tên loại công', required=True)
    code = fields.Char('Mã', help='Mã rút gọn (ví dụ: DAY, HOUR, LS, PHOTO)', index=True)
    unit = fields.Selection([
        ('day', 'Ngày'),
        ('hour', 'Giờ'),
        ('task', 'Công việc đặc thù'),
    ], string='Đơn vị tính', required=True, default='day',
    help='Đơn vị tính dùng để tính toán công (ngày/giờ/1 công việc)')
    # Giá tiền cho mỗi đơn vị (VNĐ)
    amount = fields.Monetary('Số tiền/đơn vị (VNĐ)', currency_field='company_currency_id', required=True)
    company_id = fields.Many2one('res.company', 'Công ty', default=lambda self: self.env.company)
    company_currency_id = fields.Many2one('res.currency', string='Tiền tệ công ty', related='company_id.currency_id', readonly=True)
    active = fields.Boolean('Active', default=True)
    sequence = fields.Integer('Thứ tự', default=10)

from datetime import datetime, time


# -------------------------
# HrAttendance (mở rộng)
# -------------------------
class HrAttendance(models.Model):
    _inherit = 'hr.attendance'

    date_start = fields.Datetime(
        string='Bắt đầu',
        compute='_compute_date_start_stop',
        store=True
    )
    date_stop = fields.Datetime(
        string='Kết thúc',
        compute='_compute_date_start_stop',
        store=True
    )

    @api.depends('check_in', 'check_out')
    def _compute_date_start_stop(self):
        for rec in self:
            rec.date_start = rec.check_in
            rec.date_stop = rec.check_out or (rec.check_in + timedelta(hours=8) if rec.check_in else False)

    is_late = fields.Boolean(string="Đi muộn", compute="_compute_late_early", store=True)
    is_early = fields.Boolean(string="Về sớm", compute="_compute_late_early", store=True)

    from datetime import datetime, time
    worked_hours_float = fields.Float(
        string="Worked Hours (Float)",
        compute="_compute_worked_hours_float",
        store=True
    )

    ot_done = fields.Float(
        string="OT Done",
        help="Số giờ OT thực tế",
        default=0.0
    )

    ot_balance = fields.Float(
        string="OT Balance",
        help="Số giờ OT còn lại hoặc bù trừ",
        default=0.0
    )
    
    @api.depends('check_in', 'check_out', 'attendance_type_id')
    def _compute_total_amount(self):
        HOURLY_RATE = 27000
        for rec in self:
            if rec.attendance_type_id and rec.worked_hours_float:
                rec.total_amount = rec.worked_hours_float * HOURLY_RATE
                rec.quantity = rec.worked_hours_float  # hiển thị số giờ
            else:
                rec.total_amount = 0.0
                rec.quantity = 0.0


    @api.depends("check_in", "check_out", "employee_id")
    def _compute_ot_hours(self):
        for rec in self:
            rec.ot_done = 0.0
            if not rec.check_in or not rec.check_out or not rec.employee_id:
                continue

            # Lấy timezone
            user_tz = pytz.timezone(self.env.user.tz or "UTC")
            local_in = rec.check_in.astimezone(user_tz)
            local_out = rec.check_out.astimezone(user_tz)
            d = local_in.date()

            # Tìm phân ca
            assignment = self.env['forher.shift.assignment'].search([
                ('employee_ids', 'in', rec.employee_id.id),
                ('date', '=', d),
            ], limit=1)
            if not assignment or not assignment.shift_id:
                continue

            shift = assignment.shift_id

            # Chuyển float -> time
            def float_to_time(float_hour):
                hour = int(float_hour)
                minute = int((float_hour % 1) * 60)
                return time(hour, minute)

            shift_start = float_to_time(shift.start_time)
            shift_end   = float_to_time(shift.end_time)

            planned_start = user_tz.localize(datetime.combine(d, shift_start))
            planned_end   = user_tz.localize(datetime.combine(d, shift_end))

            # OT trước ca
            ot_before = (planned_start - local_in).total_seconds() / 3600 if local_in < planned_start else 0.0
            # OT sau ca
            ot_after = (local_out - planned_end).total_seconds() / 3600 if local_out > planned_end else 0.0

            rec.ot_done = max(0.0, ot_before) + max(0.0, ot_after)


    @api.depends('check_in', 'check_out')
    def _compute_worked_hours_float(self):
        for rec in self:
            if rec.check_in and rec.check_out:
                delta = rec.check_out - rec.check_in
                rec.worked_hours_float = delta.total_seconds() / 3600.0
            else:
                rec.worked_hours_float = 0.0



    @api.constrains('check_in', 'employee_id')
    def _check_one_attendance_per_day_and_contract(self):
        for rec in self:
            if not rec.check_in or not rec.employee_id:
                continue

            # 1. Kiểm tra hợp đồng đang chạy
            contract = rec.contract_id or rec.employee_id.current_forher_contract_id
            if not contract or contract.state != 'open':
                raise ValidationError(
                    _('Nhân viên %s không có hợp đồng đang chạy. Không thể chấm công.') % rec.employee_id.name
                )

            # 2. Kiểm tra phân ca trong ngày
            user_tz = pytz.timezone(self.env.user.tz or 'UTC')
            dt = rec.check_in if rec.check_in.tzinfo else rec.check_in.replace(tzinfo=pytz.UTC)
            local_dt = dt.astimezone(user_tz)
            d = local_dt.date()

            assignments = self.env['forher.shift.assignment'].search([
                ('employee_ids', 'in', rec.employee_id.id),
                ('date', '=', d),
            ])
            if not assignments:
                raise ValidationError(
                    _('Nhân viên %s chưa được phân ca trong ngày %s. Không thể chấm công.') %
                    (rec.employee_id.name, d.strftime('%d/%m/%Y'))
                )

            # 👉 2.1: Ràng buộc giờ check_in theo ca
            def float_to_time(float_hour):
                hour = int(float_hour)
                minute = int(round((float_hour % 1) * 60))
                return time(hour, minute)

            valid_shift = False
            for assign in assignments:
                shift = assign.shift_id
                if not shift:
                    continue

                shift_start = float_to_time(shift.start_time)
                shift_end   = float_to_time(shift.end_time)

                planned_start = user_tz.localize(datetime.combine(d, shift_start))
                planned_end   = user_tz.localize(datetime.combine(d, shift_end))

                # Cho phép từ 30p trước giờ ca → hết ca
                allowed_start = planned_start - timedelta(minutes=30)
                allowed_end   = planned_end

                if allowed_start <= local_dt <= allowed_end:
                    valid_shift = True
                    break

            if not valid_shift:
                raise ValidationError(
                    _('Chưa tới giờ chấm công.') %
                    (local_dt.strftime('%H:%M'), rec.employee_id.name, d.strftime('%d/%m/%Y'))
                )

            # 3. Chặn chấm công nhiều lần trong ngày
            local_start = datetime.combine(d, time.min).replace(tzinfo=user_tz)
            local_end   = datetime.combine(d, time.max).replace(tzinfo=user_tz)
            day_start_utc = local_start.astimezone(pytz.UTC)
            day_end_utc   = local_end.astimezone(pytz.UTC)

            existing = self.search([
                ('employee_id', '=', rec.employee_id.id),
                ('id', '!=', rec.id),
                ('check_in', '>=', fields.Datetime.to_string(day_start_utc)),
                ('check_in', '<=', fields.Datetime.to_string(day_end_utc)),
            ], limit=1)
            if existing:
                raise ValidationError(
                    _('Nhân viên %s đã chấm công hôm %s. Chỉ được chấm 1 lần/ngày.') %
                    (rec.employee_id.name, d.strftime('%d/%m/%Y'))
                )

    @api.depends("check_in", "check_out", "employee_id")
    def _compute_late_early(self):
        for rec in self:
            rec.is_late = False
            rec.is_early = False

            if not rec.check_in or not rec.employee_id:
                continue

            # Lấy ngày local từ check_in
            user_tz = pytz.timezone(self.env.user.tz or "UTC")
            dt = rec.check_in if rec.check_in.tzinfo else rec.check_in.replace(tzinfo=pytz.UTC)
            local_dt = dt.astimezone(user_tz)
            d = local_dt.date()

            # Tìm ca làm việc trong ngày
            assignments = self.env['forher.shift.assignment'].search([
                ('employee_ids', 'in', rec.employee_id.id),
                ('date', '=', d),
            ], limit=1)

            if not assignments:
                continue

            shift = assignments.shift_id
            if not shift:
                continue

            # Chuyển float -> time
            def float_to_time(float_hour):
                hour = int(float_hour)
                minute = int((float_hour % 1) * 60)
                return time(hour, minute)

            shift_start = float_to_time(shift.start_time)
            shift_end   = float_to_time(shift.end_time)

            planned_start = user_tz.localize(datetime.combine(d, shift_start))
            planned_end   = user_tz.localize(datetime.combine(d, shift_end))

            # Check đi trễ
            if rec.check_in.astimezone(user_tz) > planned_start:
                rec.is_late = True

            # Check về sớm
            if rec.check_out and rec.check_out.astimezone(user_tz) < planned_end:
                rec.is_early = True



    # === ForHer integration fields === tổng quan chấm công
    branch_id = fields.Many2one(
        'res.company',
        string='Chi nhánh',
        related='employee_id.company_id',
        store=True,
        readonly=True,
        help="Chi nhánh làm việc của nhân viên"
    )
    parent_company_id = fields.Many2one(
        'res.company',
        string='Công ty mẹ',
        related='branch_id.parent_id',
        store=True,
        readonly=True,
        help="Công ty mẹ Forher"
    )

    # Link to current ForHer contract and contract type (thay cho employee_type)
    contract_id = fields.Many2one(
        'forher.hr.contract',
        string='Hợp đồng hiện tại',
        related='employee_id.current_forher_contract_id',
        store=True,
        readonly=True
    )
    contract_type_id = fields.Many2one(
        'hr.contract.type',
        string='Loại hợp đồng',
        related='contract_id.contract_type_id',
        store=True,
        readonly=True
    )


    # Loại công (ForHer)
    attendance_type_id = fields.Many2one(
        'forher.attendance.type',
        string='Loại công',
        index=True,
        help='Loại công: ngày, giờ, livestream, chụp hình, quay clip...'
    )

    # Ai ghi nhận (Quản lý chi nhánh hoặc Kế toán)
    recorded_by = fields.Many2one('res.users', string='Người ghi nhận', default=lambda self: self.env.user, readonly=True)
    # Dạng public để NV đối soát
    is_public = fields.Boolean('Công public (NV có thể đối soát)', default=True)

    # === additional attendance fields ===
    date = fields.Date('Ngày', compute='_compute_date', store=True, index=True)
    state = fields.Selection([
        ('draft', 'Nháp'),
        ('confirmed', 'Đã xác nhận'),
        ('validated', 'Đã duyệt'),
        ('rejected', 'Từ chối')
    ], string='Trạng thái', default='confirmed', tracking=True)

    note = fields.Text('Ghi chú')
    check_in_note = fields.Char('Ghi chú vào', size=200)
    check_out_note = fields.Char('Ghi chú ra', size=200)

    check_in_location = fields.Char('Vị trí check-in')
    check_out_location = fields.Char('Vị trí check-out')

    # check_in_ip = fields.Char('IP check-in')  # Đã bỏ không sử dụng
    # check_out_ip = fields.Char('IP check-out')  # Đã bỏ không sử dụng

    # Số lượng theo unit: nếu unit = hour thì lưu giờ (float), nếu day thì số ngày (float), nếu task thì số công (float)
    quantity = fields.Float('Số lượng', default=1.0,
                            help='Số lượng đơn vị tương ứng với attendance_type (ví dụ 1 ngày, 3.5 giờ, 1 công)')

    # Tổng tiền = quantity * amount (tự động tính)
    total_amount = fields.Monetary('Tổng tiền (VNĐ)', compute='_compute_total_amount', store=True, currency_field='company_currency_id')
    company_currency_id = fields.Many2one('res.currency', string='Tiền tệ công ty', related='branch_id.currency_id', readonly=True)

    # === COMPUTED FIELDS ===
    @api.depends('check_in')
    def _compute_date(self):
        """Tính toán ngày từ thời gian check-in (fix timezone)"""
        for record in self:
            if record.check_in:
                user_tz = pytz.timezone(self.env.user.tz or 'UTC')
                # safe convert datetime assumed UTC naive -> localize via replace
                dt = record.check_in
                if dt.tzinfo is None:
                    dt = dt.replace(tzinfo=pytz.UTC)
                check_in_local = dt.astimezone(user_tz)
                record.date = check_in_local.date()
            else:
                record.date = False

    # === VALIDATION & CONSTRAINTS ===
    @api.constrains('check_in', 'check_out', 'employee_id')
    def _check_validity(self):
        """Kiểm tra tính hợp lệ của bản ghi chấm công"""
        for attendance in self:
            if attendance.employee_id and not attendance.branch_id:
                raise ValidationError(
                    _('Nhân viên %s chưa được gán chi nhánh. Không thể chấm công.') % attendance.employee_id.name
                )

            # Nếu check_in có, kiểm tra có bản ghi chưa check_out cùng ngày hay overlap
            if attendance.check_in:
                # compute day range in UTC for safety
                # convert check_in to date (UTC)
                dt = attendance.check_in
                if dt.tzinfo is None:
                    dt = dt.replace(tzinfo=pytz.UTC)
                dt_utc = dt.astimezone(pytz.UTC)
                day_start = dt_utc.replace(hour=0, minute=0, second=0, microsecond=0)
                day_end = day_start + timedelta(days=1)
                domain = [
                    ('employee_id', '=', attendance.employee_id.id),
                    ('id', '!=', attendance.id),
                    ('check_in', '>=', fields.Datetime.to_string(day_start)),
                    ('check_in', '<', fields.Datetime.to_string(day_end)),
                    ('check_out', '=', False)
                ]
                existing = self.search(domain, limit=1)
                if existing:
                    raise ValidationError(
                        _('Nhân viên %s đã có bản ghi chấm công chưa kết thúc trong ngày %s') % (attendance.employee_id.name, attendance.date or ''))
    # === METHODS ===
    def action_confirm(self):
        for record in self:
            if record.state == 'draft':
                record.state = 'confirmed'
        return True

    def action_validate(self):
        if not self.env.user.has_group('forher_attendance.group_attendance_manager'):
            raise UserError(_('Bạn không có quyền duyệt chấm công.'))
        for record in self:
            if record.state == 'confirmed':
                record.state = 'validated'
        return True

    def action_reject(self):
        if not self.env.user.has_group('forher_attendance.group_attendance_manager'):
            raise UserError(_('Bạn không có quyền từ chối chấm công.'))
        for record in self:
            record.state = 'rejected'
        return True

    @api.model
    def create_attendance(
        self, employee_id, check_type="check_in", note=None, location=None,
        attendance_type_id=None, quantity=1.0
    ):
        employee = self.env["hr.employee"].browse(employee_id)
        if not employee.exists():
            raise UserError(_("Nhân viên không tồn tại."))
        if not employee.company_id:
            raise UserError(_("Nhân viên %s chưa được gán chi nhánh.") % employee.name)

        user = self.env.user
        if not (user.has_group("forher_company_overview.forher_group_branch_manager") or
                user.has_group("forher_company_overview.forher_group_accountant")):
            raise UserError(_("Bạn không có quyền ghi nhận chấm công."))

        # === 1. Kiểm tra hợp đồng đang chạy ===
        contract = employee.current_forher_contract_id
        if not contract or contract.state != "open":
            raise UserError(_("Nhân viên %s không có hợp đồng đang chạy.") % employee.name)

        # === 2. Xác định ngày local (theo timezone user) ===
        user_tz = pytz.timezone(user.tz or "UTC")
        now_utc = datetime.now(pytz.UTC)
        now_local = now_utc.astimezone(user_tz)
        today_local = now_local.date()

        # === 3. Kiểm tra phân ca (bắt buộc) ===
        assignments = self.env['forher.shift.assignment'].search([
            ('employee_ids', 'in', employee.id),
            ('date', '=', today_local),
        ])
        if not assignments:
            raise UserError(_("Nhân viên %s không có ca làm trong ngày %s. Không thể chấm công.") %
                            (employee.name, today_local.strftime("%d/%m/%Y")))

        assignment = assignments[0]
        shift = assignment.shift_id
        if not shift:
            raise UserError(_("Phân ca không có thông tin ca làm việc."))

        # build datetime từ shift.start_time / end_time
        start_hour = int(shift.start_time)
        start_minute = int((shift.start_time % 1) * 60)
        end_hour = int(shift.end_time)
        end_minute = int((shift.end_time % 1) * 60)

        planned_start = user_tz.localize(datetime.combine(today_local, time(start_hour, start_minute)))
        planned_end = user_tz.localize(datetime.combine(today_local, time(end_hour, end_minute)))

        # === 4. Check đã chấm công trong ngày chưa ===
        local_start = datetime.combine(today_local, time.min).replace(tzinfo=user_tz)
        local_end = datetime.combine(today_local, time.max).replace(tzinfo=user_tz)
        day_start_utc = local_start.astimezone(pytz.UTC)
        day_end_utc = local_end.astimezone(pytz.UTC)

        now = datetime.now(pytz.UTC)
        vals = {
            "employee_id": employee_id,
            "attendance_type_id": attendance_type_id,
            "recorded_by": user.id,
        }

        if check_type == "check_in":
            assignment = assignments[0]
            shift = assignment.shift_id
            if not shift:
                raise UserError(_("Nhân viên %s chưa có ca làm.") % employee.name)

            shift_date = assignment.date
            user_tz = pytz.timezone(user.tz or "UTC")

            # Convert float → time
            shift_start = self.float_to_time(shift.start_time)
            shift_end = self.float_to_time(shift.end_time)

            # Ghép ngày + giờ
            planned_start = user_tz.localize(datetime.combine(shift_date, shift_start))
            planned_end = user_tz.localize(datetime.combine(shift_date, shift_end))

            # Giờ hiện tại (máy user)
            now = datetime.now(user_tz)

            # Chỉ cho phép check-in từ 30p trước giờ ca đến giờ kết thúc ca
            allowed_start = planned_start - timedelta(minutes=30)
            allowed_end = planned_end

            if not (allowed_start <= now <= allowed_end):
                raise UserError(_("Bạn chỉ có thể chấm công từ %s đến %s cho ca %s.") % (
                    allowed_start.strftime("%H:%M"),
                    allowed_end.strftime("%H:%M"),
                    shift.name
                ))

    @api.model
    def cron_aggregate_attendance_monthly(self, year=None, month=None):
        """Tổng hợp công — gợi ý: gọi cron vào 1-3 tháng sau"""
        today = date.today()
        if not year:
            year = today.year
        if not month:
            month = today.month - 1 or 12
            if month == 12:
                year = year - 1
        # first and last day UTC
        from calendar import monthrange
        first = date(year, month, 1)
        last = date(year, month, monthrange(year, month)[1])
        domain = [
            ('date', '>=', first),
            ('date', '<=', last),
            ('state', 'in', ['confirmed', 'validated'])
        ]
        attendances = self.search(domain)
        # build summary per employee
        summary = {}
        for att in attendances:
            emp = att.employee_id
            key = (emp.id, att.attendance_type_id.id if att.attendance_type_id else False)
            if key not in summary:
                summary[key] = {'employee': emp, 'type': att.attendance_type_id, 'quantity': 0.0, 'amount': 0.0}
            summary[key]['quantity'] += att.quantity or 0.0
            summary[key]['amount'] += att.total_amount or 0.0
        # You may write summaries to a model for persistence or email to accountant; here we just return
        return summary


# -------------------------
# HrEmployee adjustments
# -------------------------
class HrEmployee(models.Model):
    _inherit = 'hr.employee'

    # Mã nhân viên giữ nguyên hoặc override bằng ir.sequence (gợi ý)
    employee_code = fields.Char('Mã nhân viên', readonly=True, copy=False, default='New')

    # PIN cho kiosk chấm công
    pin = fields.Char('PIN Kiosk', size=6, help='Mã PIN 4-6 số để chấm công qua kiosk')

    # Work mode và quy định số ngày công
    work_mode = fields.Selection([('fulltime', 'Fulltime'), ('parttime', 'Parttime')], string='Kiểu làm việc', default='fulltime')
    # Số ngày chuẩn (calculated): nếu fulltime => days_in_month - 4 ; parttime => 0 (không áp dụng)
    standard_work_days = fields.Integer('Số ngày công quy định', compute='_compute_standard_work_days', store=True)

    # ForHer contracts
    forher_contract_ids = fields.One2many('forher.hr.contract', 'employee_id', string='Hợp đồng ForHer')
    current_forher_contract_id = fields.Many2one('forher.hr.contract', string='Hợp đồng hiện tại', compute='_compute_current_forher_contract', store=True)

    @api.depends('forher_contract_ids', 'forher_contract_ids.state')
    def _compute_current_forher_contract(self):
        for emp in self:
            contracts = emp.forher_contract_ids.filtered(lambda c: c.state in ['open', 'waiting_approval'])
            emp.current_forher_contract_id = contracts[:1].id if contracts else False

    @api.depends('work_mode')
    def _compute_standard_work_days(self):
        for emp in self:
            if emp.work_mode == 'fulltime':
                # tính theo tháng hiện tại
                today = date.today()
                import calendar
                days_in_month = calendar.monthrange(today.year, today.month)[1]
                emp.standard_work_days = days_in_month - 4
            else:
                emp.standard_work_days = 0

    # Attendance stats
    attendance_count = fields.Integer('Số lần chấm công', compute='_compute_attendance_count')

    @api.depends('attendance_ids')
    def _compute_attendance_count(self):
        for employee in self:
            employee.attendance_count = len(employee.attendance_ids)

    def action_view_attendance(self):
        self.ensure_one()
        action = self.env['ir.actions.act_window']._for_xml_id('hr_attendance.hr_attendance_action')
        action['domain'] = [('employee_id', '=', self.id)]
        action['context'] = {'default_employee_id': self.id}
        return action

# -*- coding: utf-8 -*-
from odoo import models, fields, api, _
from odoo.exceptions import ValidationError
from datetime import time, timedelta

# =====================
# CA LÀM VIỆC
# =====================
class ForHerShift(models.Model):
    _name = "forher.shift"
    _description = "Ca làm việc ForHer"
    _order = "start_time"

    name = fields.Char("Tên ca", required=True)
    code = fields.Char("Mã ca", required=True)
    start_time = fields.Float("Giờ bắt đầu", required=True)  # 8.5 = 8:30
    end_time = fields.Float("Giờ kết thúc", required=True)   # 16 = 16h
    duration = fields.Float("Thời lượng (giờ)", compute="_compute_duration", store=True)
    active = fields.Boolean(default=True)
    color = fields.Integer("Màu", default=2)
    note = fields.Text("Ghi chú")   
    company_id = fields.Many2one(
    "res.company", string="Chi nhánh", required=True, default=lambda self: self.env.company
)


    @api.depends("start_time", "end_time")
    def _compute_duration(self):
        for rec in self:
            rec.duration = rec.end_time - rec.start_time if rec.end_time > rec.start_time else 0.0


# =====================
# PHÂN CA
# =====================
class ForHerShiftAssignment(models.Model):
    _name = "forher.shift.assignment"
    _description = "Phân ca cho nhân viên"
    _order = "date, shift_id"

    employee_ids = fields.Many2many(
        "hr.employee", string="Nhân viên", required=True)
    shift_id = fields.Many2one("forher.shift", string="Ca làm việc", required=True)
    date = fields.Date("Ngày làm việc", required=True, index=True)
    company_id = fields.Many2one(
        "res.company", string="Chi nhánh", related="shift_id.company_id", store=True)
    color = fields.Integer(related="shift_id.color", store=True)

    date_start = fields.Datetime("Bắt đầu ca", compute="_compute_date_start_stop", store=True)
    date_stop = fields.Datetime("Kết thúc ca", compute="_compute_date_start_stop", store=True)

    from datetime import time

    name = fields.Char("Tên hiển thị", compute='_compute_name', store=True)

    @api.depends('shift_id', 'date')
    def _compute_name(self):
        for rec in self:
            if rec.shift_id:
                # Lấy giờ bắt đầu và kết thúc
                start_hour = int(rec.shift_id.start_time)
                start_minute = int((rec.shift_id.start_time - start_hour) * 60)
                end_hour = int(rec.shift_id.end_time)
                end_minute = int((rec.shift_id.end_time - end_hour) * 60)
                start_str = f"{start_hour:02d}:{start_minute:02d}"
                end_str = f"{end_hour:02d}:{end_minute:02d}"

                # Hiển thị tên ca + giờ + ngày
                rec.name = f"{rec.shift_id.name} ({start_str}-{end_str}) ({rec.date})"
            else:
                rec.name = ""


    @api.depends('date', 'shift_id')
    def _compute_date_start_stop(self):
        for rec in self:
            if rec.date and rec.shift_id:
                start_hour = int(rec.shift_id.start_time)
                start_minute = int((rec.shift_id.start_time - start_hour) * 60)
                end_hour = int(rec.shift_id.end_time)
                end_minute = int((rec.shift_id.end_time - end_hour) * 60)
                rec.date_start = datetime.combine(rec.date, time(start_hour, start_minute))
                rec.date_stop = datetime.combine(rec.date, time(end_hour, end_minute))
            else:
                rec.date_start = rec.date_stop = False

    # Loại bỏ SQL constraint vì Many2many sẽ tạo nhiều bản ghi riêng biệt khi lưu
    def name_get(self):
        result = []
        for rec in self:
            names = ", ".join(emp.name for emp in rec.employee_ids)
            result.append((rec.id, f"{names} - {rec.shift_id.name} ({rec.date})"))
        return result


# =====================
# QUY ĐỊNH & VI PHẠM
# =====================
class ForHerViolationRule(models.Model):
    _name = "forher.violation.rule"
    _description = "Quy định vi phạm"

    code = fields.Char("Mã", required=True)
    name = fields.Char("Tên vi phạm", required=True)
    penalty_type = fields.Selection([
        ("warning", "Cảnh cáo"),
        ("salary_deduction", "Trừ lương"),
        ("rank_deduction", "Trừ xếp loại tháng"),
    ], string="Hình thức xử lý", required=True)
    amount = fields.Float("Mức phạt (VNĐ)", default=0.0)


class ForHerViolationRecord(models.Model):
    _name = "forher.violation.record"
    _description = "Ghi nhận vi phạm"

    employee_id = fields.Many2one("hr.employee", string="Nhân viên", required=True)
    attendance_id = fields.Many2one("hr.attendance", string="Bản ghi công")
    violation_rule_id = fields.Many2one("forher.violation.rule", string="Vi phạm", required=True)
    date = fields.Date("Ngày", default=fields.Date.today)
    note = fields.Text("Ghi chú")
    state = fields.Selection([
        ("draft", "Nháp"),
        ("confirmed", "Đã xác nhận"),
        ("deducted", "Đã xử lý")
    ], default="draft", string="Trạng thái")


# =====================
# CRON CHECK VI PHẠM
# =====================
class HrAttendanceInherit(models.Model):
    _inherit = "hr.attendance"

    is_late = fields.Boolean("Đi trễ")
    is_early = fields.Boolean("Về sớm")

    def action_check_violation(self):
        """Check vi phạm đi trễ theo tháng"""
        rules = {
            1: self.env.ref("forher_attendance.rule_warning", raise_if_not_found=False),
            2: self.env.ref("forher_attendance.rule_salary", raise_if_not_found=False),
            3: self.env.ref("forher_attendance.rule_rank", raise_if_not_found=False),
        }
        # group by employee + tháng
        employees = self.env["hr.employee"].search([])
        for emp in employees:
            attendances = self.search([("employee_id", "=", emp.id), ("is_late", "=", True)])
            late_count = len(attendances)
            if late_count >= 1:
                if late_count == 1 and rules[1]:
                    self.env["forher.violation.record"].create({
                        "employee_id": emp.id,
                        "attendance_id": attendances[0].id,
                        "violation_rule_id": rules[1].id,
                        "note": "Đi trễ lần 1 trong tháng"
                    })
                elif late_count == 2 and rules[2]:
                    self.env["forher.violation.record"].create({
                        "employee_id": emp.id,
                        "attendance_id": attendances[-1].id,
                        "violation_rule_id": rules[2].id,
                        "note": "Đi trễ lần 2 trong tháng"
                    })
                elif late_count >= 3 and rules[3]:
                    self.env["forher.violation.record"].create({
                        "employee_id": emp.id,
                        "attendance_id": attendances[-1].id,
                        "violation_rule_id": rules[3].id,
                        "note": f"Đi trễ lần {late_count} trong tháng"
                    })
