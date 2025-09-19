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
    
    def _compute_worked_hours_float(self):
        for rec in self:
            rec.worked_hours_float = rec.worked_hours

    @api.constrains('check_in', 'employee_id')
    def _check_one_attendance_per_day_and_contract(self):
        """Ngăn chặn chấm công nhiều lần trong ngày (theo TZ user) + hợp đồng phải đang 'open'."""
        for rec in self:
            if not rec.check_in or not rec.employee_id:
                continue

            # Hợp đồng phải 'open'
            contract = rec.contract_id or rec.employee_id.current_forher_contract_id
            if not contract or contract.state != 'open':
                raise ValidationError(
                    _('Nhân viên %s không có hợp đồng đang chạy. Không thể chấm công.') % rec.employee_id.name
                )

            # Mốc ngày theo TZ user -> đổi về UTC để đưa vào domain
            user_tz = pytz.timezone(self.env.user.tz or 'UTC')
            dt = rec.check_in
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=pytz.UTC)
            local_dt = dt.astimezone(user_tz)
            d = local_dt.date()
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

            contract = rec.contract_id or rec.employee_id.contract_id
            if not contract or not rec.check_in:
                continue

            calendar = contract.resource_calendar_id or rec.employee_id.resource_calendar_id
            start_time = time(8, 0, 0)
            end_time = time(17, 0, 0)

            if calendar:
                weekday = rec.check_in.weekday()
                attendances = calendar.attendance_ids.filtered(
                    lambda a: int(a.dayofweek) == weekday and (a.name != 'Break')
                )
                if attendances:
                    min_hour = min(attendances.mapped('hour_from'))
                    start_hour = int(min_hour)
                    start_minute = int((min_hour - start_hour) * 60)
                    start_time = time(start_hour, start_minute)

                    max_hour = max(attendances.mapped('hour_to'))
                    end_hour = int(max_hour)
                    end_minute = int((max_hour - end_hour) * 60)
                    end_time = time(end_hour, end_minute)

            if rec.check_in.time() > start_time:
                rec.is_late = True
                rec.attendance_type_id = self.env.ref("forher_attendance.type_ot")

            if rec.check_out and rec.check_out.time() < end_time:
                rec.is_early = True
                rec.attendance_type_id = self.env.ref("forher_attendance.type_ot")


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

    @api.depends('attendance_type_id', 'quantity')
    def _compute_total_amount(self):
        for rec in self:
            if rec.attendance_type_id:
                rec.total_amount = (rec.quantity or 0.0) * (rec.attendance_type_id.amount or 0.0)
            else:
                rec.total_amount = 0.0

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
        """
        API để tạo bản ghi chấm công (dùng cho mobile/web)
        - Chỉ cho phép 1 lần chấm công/ngày
        - Chỉ cho phép hợp đồng Running (state='open')
        - Hỗ trợ phân biệt fulltime / parttime
        """

        # ================== 1. Lấy nhân viên ==================
        employee = self.env["hr.employee"].browse(employee_id)
        if not employee.exists():
            raise UserError(_("Nhân viên không tồn tại."))

        if not employee.company_id:
            raise UserError(_("Nhân viên %s chưa được gán chi nhánh.") % employee.name)

        # ================== 2. Phân quyền ==================
        user = self.env.user
        if not (user.has_group("forher_company_overview.forher_group_branch_manager") or
                user.has_group("forher_company_overview.forher_group_accountant")):
            raise UserError(_("Bạn không có quyền ghi nhận chấm công."))

        # ================== 3. Kiểm tra hợp đồng ==================
        contract = employee.current_forher_contract_id
        if not contract or contract.state != "open":
            raise UserError(_("Nhân viên %s không có hợp đồng đang chạy.") % employee.name)

        # ================== 4. Xác định ngày hiện tại ==================
        user_tz = pytz.timezone(user.tz or "UTC")
        now_utc = datetime.now(pytz.UTC)
        today_local = now_utc.astimezone(user_tz).date()

        local_start = datetime.combine(today_local, time.min).replace(tzinfo=user_tz)
        local_end = datetime.combine(today_local, time.max).replace(tzinfo=user_tz)
        day_start_utc = local_start.astimezone(pytz.UTC)
        day_end_utc = local_end.astimezone(pytz.UTC)

        # ================== 5. Chặn chấm công trùng trong ngày ==================
        if check_type == "check_in":
            existing_today = self.search([
                ("employee_id", "=", employee_id),
                ("check_in", ">=", fields.Datetime.to_string(day_start_utc)),
                ("check_in", "<=", fields.Datetime.to_string(day_end_utc)),
            ], limit=1)
            if existing_today:
                raise UserError(_("Nhân viên %s đã chấm công hôm nay.") % employee.name)

        # ================== 6. Chuẩn bị dữ liệu ==================
        vals = {
            "employee_id": employee_id,
            "attendance_type_id": attendance_type_id,
            "recorded_by": user.id,
            "check_in_note": note if check_type == "check_in" else None,
            "check_out_note": note if check_type == "check_out" else None,
            "check_in_location": location if check_type == "check_in" else None,
            "check_out_location": location if check_type == "check_out" else None,
        }

        # ================== 7. Logic Fulltime ==================
        if contract.contract_type_id and contract.contract_type_id.code == "fulltime":
            calendar = contract.calendar_id
            if not calendar:
                raise UserError(_("Hợp đồng %s chưa được gán lịch làm việc.") % contract.name)

            weekday = today_local.weekday()
            attendances = calendar.attendance_ids.filtered(lambda a: int(a.dayofweek) == weekday)
            if not attendances:
                raise UserError(_("Không tìm thấy ca làm việc cho %s trong ngày %s") %
                                (employee.name, today_local.strftime("%d/%m/%Y")))

            att = attendances[0]  # TODO: mở rộng nhiều ca
            start_hour = int(att.hour_from)
            start_minute = int((att.hour_from - start_hour) * 60)
            end_hour = int(att.hour_to)
            end_minute = int((att.hour_to - end_hour) * 60)

            planned_start = datetime.combine(today_local, time(start_hour, start_minute)).replace(tzinfo=user_tz).astimezone(pytz.UTC)
            planned_end = datetime.combine(today_local, time(end_hour, end_minute)).replace(tzinfo=user_tz).astimezone(pytz.UTC)

            if check_type == "check_in":
                now = fields.Datetime.now()
                vals["check_in"] = now
                vals["quantity"] = 0.0
                vals["is_late"] = now > planned_start
                return self.create(vals)

            else:  # check_out
                attendance = self.search([
                    ("employee_id", "=", employee_id),
                    ("check_out", "=", False)
                ], limit=1, order="check_in desc")

                if not attendance:
                    raise UserError(_("Không tìm thấy bản ghi check-in để kết thúc."))

                now = fields.Datetime.now()
                delta_hours = (now - attendance.check_in).total_seconds() / 3600.0

                vals_update = {
                    "check_out": now,
                    "check_out_note": note,
                    "check_out_location": location,
                    "quantity": round(delta_hours, 2),
                }

                if now < planned_end:
                    vals_update["is_early"] = True

                attendance.write(vals_update)
                attendance.invalidate_cache()
                return attendance

        # ================== 8. Logic Parttime ==================
        elif contract.contract_type_id and contract.contract_type_id.code == "parttime":
            if check_type == "check_in":
                vals["check_in"] = fields.Datetime.now()
                vals["quantity"] = 0.0
                return self.create(vals)
            else:
                attendance = self.search([
                    ("employee_id", "=", employee_id),
                    ("check_out", "=", False)
                ], limit=1, order="check_in desc")

                if not attendance:
                    raise UserError(_("Không tìm thấy bản ghi check-in để kết thúc."))

                now = fields.Datetime.now()
                vals_update = {
                    "check_out": now,
                    "check_out_note": note,
                    "check_out_location": location,
                    # parttime: tính công cố định (vd: quantity từ tham số)
                    "quantity": quantity or attendance.quantity,
                }
                attendance.write(vals_update)
                attendance.invalidate_cache()
                return attendance

        # ================== 9. Loại hợp đồng khác ==================
        else:
            raise UserError(_("Hợp đồng %s không xác định loại fulltime/parttime.") % contract.name)


    # def _get_client_ip(self):  # Đã bỏ không sử dụng IP
    #     if request:
    #         return request.httprequest.environ.get('REMOTE_ADDR', '') or ''
    #     return ''

    # Helper: tổng hợp công cho 1 tháng (có thể gọi qua cron)
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
