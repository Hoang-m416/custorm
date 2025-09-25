from datetime import timedelta

from odoo import Command, _, api, fields, models
from odoo.exceptions import UserError, ValidationError


class ForherPayslipLine(models.Model):
    _name = 'forher.payslip.line'
    _description = 'Forher Payslip Line'
    _order = 'sequence, id'

    payslip_id = fields.Many2one('forher.payslip', required=True, ondelete='cascade')
    rule_id = fields.Many2one('forher.salary.rule', string='Salary Rule', ondelete='set null')
    name = fields.Char(required=True)
    code = fields.Char(required=True)
    sequence = fields.Integer(default=10)
    rule_type = fields.Selection([
        ('basic', 'Basic'),
        ('allowance', 'Allowance'),
        ('deduction', 'Deduction'),
        ('other', 'Other'),
    ], required=True, default='other')
    quantity = fields.Float(default=1.0, digits='Payroll')
    rate = fields.Float(default=100.0, digits='Payroll')
    amount = fields.Monetary(currency_field='currency_id', digits='Payroll')
    note = fields.Char()
    currency_id = fields.Many2one('res.currency', related='payslip_id.currency_id', store=True, readonly=True)


class ForherPayslip(models.Model):
    _name = 'forher.payslip'
    _description = 'Forher Payslip'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'date_from desc, employee_id'

    name = fields.Char(default='New', readonly=True, copy=False, tracking=True)
    employee_id = fields.Many2one('hr.employee', required=True, tracking=True)
    contract_id = fields.Many2one('forher.hr.contract', required=True, tracking=True)
    structure_id = fields.Many2one('forher.salary.structure', required=True, tracking=True)
    run_id = fields.Many2one('forher.payslip.run', string='Payroll Batch', tracking=True, ondelete='set null')
    date_from = fields.Date(required=True, tracking=True)
    date_to = fields.Date(required=True, tracking=True)
    state = fields.Selection([
        ('draft', 'Draft'),
        ('computed', 'Computed'),
        ('confirmed', 'Confirmed'),
        ('done', 'Done'),
        ('cancelled', 'Cancelled'),
    ], default='draft', tracking=True)
    line_ids = fields.One2many('forher.payslip.line', 'payslip_id', copy=False)
    company_id = fields.Many2one('res.company', required=True, default=lambda self: self.env.company)
    currency_id = fields.Many2one('res.currency', related='company_id.currency_id', readonly=True, store=True)
    total_gross = fields.Monetary(currency_field='currency_id', compute='_compute_totals', store=True)
    total_deduction = fields.Monetary(currency_field='currency_id', compute='_compute_totals', store=True)
    total_net = fields.Monetary(currency_field='currency_id', compute='_compute_totals', store=True)

    sales_total_amount = fields.Monetary(currency_field='currency_id', compute='_compute_sales_metrics', store=True)
    sales_products_count = fields.Integer(string='Products sold', compute='_compute_sales_metrics', store=True)

    worked_hours_total = fields.Float(string='Worked hours', digits='Payroll', compute='_compute_attendance_metrics', store=True)
    worked_day_count = fields.Float(string='Worked days', digits='Payroll', compute='_compute_attendance_metrics', store=True)
    auto_leave_day_count = fields.Float(string='Leave days (auto)', digits='Payroll', compute='_compute_attendance_metrics', store=True)

    leave_days = fields.Float(string='Paid leave days', default=0.0, help='Number of paid leave days to include in the payroll computation. Leave 0 to use automatic value.')
    ot_normal_hours = fields.Float(string='OT hours (standard)', default=0.0, digits='Payroll')
    ot_holiday_hours = fields.Float(string='OT hours (holiday)', default=0.0, digits='Payroll')
    abc_rating = fields.Selection([
        ('A', 'A'),
        ('B', 'B'),
        ('C', 'C'),
    ], string='ABC rating', default='C')
    advance_amount = fields.Monetary(string='Advance payment', currency_field='currency_id', default=0.0)
    penalty_amount = fields.Monetary(string='Penalty', currency_field='currency_id', default=0.0)

    _sql_constraints = [
        ('check_dates', 'CHECK(date_from <= date_to)', 'The start date must be before the end date.'),
    ]

    @api.model
    def create(self, vals):
        if vals.get('name') in (False, '/', 'New'):
            vals['name'] = self.env['ir.sequence'].next_by_code('forher.payslip') or 'New'
        if vals.get('contract_id'):
            contract = self.env['forher.hr.contract'].browse(vals['contract_id'])
            vals.setdefault('company_id', contract.company_id.id or self.env.company.id)
            if contract.salary_structure_id:
                vals.setdefault('structure_id', contract.salary_structure_id.id)
        return super().create(vals)

    def write(self, vals):
        if vals.get('contract_id'):
            contract = self.env['forher.hr.contract'].browse(vals['contract_id'])
            vals.setdefault('company_id', contract.company_id.id)
            if 'structure_id' not in vals and contract.salary_structure_id:
                vals['structure_id'] = contract.salary_structure_id.id
        return super().write(vals)

    @api.depends('line_ids.amount', 'line_ids.rule_type')
    def _compute_totals(self):
        for slip in self:
            gross = sum(line.amount for line in slip.line_ids if line.rule_type != 'deduction')
            deduction = sum(line.amount for line in slip.line_ids if line.rule_type == 'deduction')
            slip.total_gross = gross
            slip.total_deduction = deduction
            slip.total_net = gross - deduction

    @api.depends('run_id', 'employee_id', 'date_from', 'date_to', 'company_id')
    def _compute_sales_metrics(self):
        for slip in self:
            sales_records = slip._get_sales_records()
            slip.sales_total_amount = sum(sales_records.mapped('amount'))
            slip.sales_products_count = sum(sales_records.mapped('products_sold'))

    @api.depends('employee_id', 'date_from', 'date_to')
    def _compute_attendance_metrics(self):
        for slip in self:
            if not slip.employee_id or not slip.date_from or not slip.date_to:
                slip.worked_hours_total = 0.0
                slip.worked_day_count = 0.0
                slip.auto_leave_day_count = 0.0
                continue

            Attendance = self.env['hr.attendance'].sudo()
            attendances = Attendance.search([
                ('employee_id', '=', slip.employee_id.id),
                ('check_in', '>=', slip.date_from),
                ('check_in', '<=', slip.date_to),
            ])

            # Tổng giờ làm từ quantity
            total_hours = 0.0
            for rec in attendances:
                qty = rec.quantity or 0.0
                unit = getattr(rec, 'attendance_type', 'hour')
                if unit == 'hour':
                    total_hours += qty
                elif unit in ('day', 'task'):
                    total_hours += qty * 8  # giả định 1 ngày/1 công = 8 giờ

            # Số ngày làm việc thực tế dựa trên check-in
            attendance_days = {fields.Datetime.to_datetime(rec.check_in).date() for rec in attendances if rec.check_in}
            total_days = len(attendance_days)

            # Ngày nghỉ tự động
            leave_days = slip._get_attendance_summary().get('leave_days', 0.0)

            # Gán vào payslip
            slip.worked_hours_total = total_hours
            slip.worked_day_count = total_days
            slip.auto_leave_day_count = leave_days




    @api.onchange('contract_id')
    def _onchange_contract_id(self):
        for slip in self:
            if slip.contract_id:
                slip.employee_id = slip.contract_id.employee_id
                if slip.contract_id.salary_structure_id:
                    slip.structure_id = slip.contract_id.salary_structure_id
                if slip.contract_id.company_id:
                    slip.company_id = slip.contract_id.company_id

    @api.onchange('employee_id')
    def _onchange_employee_id(self):
        for slip in self:
            if slip.employee_id:
                contract = slip.employee_id.forher_contract_id or self.env['forher.hr.contract'].search([
                    ('employee_id', '=', slip.employee_id.id),
                    ('state', 'in', ['open', 'waiting_approval']),
                ], limit=1, order='date_start desc')
                if contract:
                    slip.contract_id = contract
                    if contract.salary_structure_id:
                        slip.structure_id = contract.salary_structure_id
                    if contract.company_id:
                        slip.company_id = contract.company_id

    def action_compute_sheet(self):
        for slip in self:
            slip._compute_lines()
        return True

    def _compute_lines(self):
        for slip in self:
            structure = slip.structure_id or slip.contract_id.salary_structure_id
            if not structure:
                raise ValidationError(
                    _('Salary structure is missing for %(employee)s. Assign a structure on the contract.', employee=slip.employee_id.display_name)
                )
            slip.structure_id = structure

            localdict = slip._prepare_localdict()
            categories = localdict['categories']
            rules_buckets = localdict['rules']
            commands = [Command.clear()]

            for rule in structure.rule_ids.sorted('sequence'):
                localdict.update({'quantity': 1.0, 'rate': 100.0})
                amount, quantity, rate, skip_line = rule._compute_rule_amount(localdict)
                if skip_line:
                    rules_buckets[rule.code] = 0.0
                    localdict[rule.code] = 0.0
                    continue

                amount = amount or 0.0
                if rule.rule_type == 'deduction':
                    stored_amount = abs(amount)
                    signed_amount = -stored_amount
                else:
                    stored_amount = amount
                    signed_amount = stored_amount

                if not stored_amount and not rule.always_include:
                    rules_buckets[rule.code] = signed_amount
                    localdict[rule.code] = signed_amount
                    continue

                commands.append(Command.create({
                    'name': rule.name,
                    'code': rule.code,
                    'rule_id': rule.id,
                    'sequence': rule.sequence,
                    'rule_type': rule.rule_type,
                    'quantity': quantity,
                    'rate': rate,
                    'amount': stored_amount,
                }))

                rules_buckets[rule.code] = signed_amount
                localdict[rule.code] = signed_amount
                categories[rule.rule_type] = categories.get(rule.rule_type, 0.0) + signed_amount

            slip.line_ids = commands
            if slip.state == 'draft':
                slip.state = 'computed'

    def action_confirm(self):
        for slip in self:
            if slip.state not in ('computed', 'draft'):
                continue
            if not slip.line_ids:
                raise UserError(_('Please compute the payslip before confirming.'))
            slip.state = 'confirmed'
        return True

    def action_done(self):
        for slip in self:
            if slip.state not in ('confirmed', 'computed'):
                continue
            slip.state = 'done'
        return True

    def action_cancel(self):
        for slip in self:
            slip.state = 'cancelled'
        return True

    def action_reset_to_draft(self):
        for slip in self:
            slip.line_ids = [Command.clear()]
            slip.state = 'draft'
        return True

    def _prepare_localdict(self):
        self.ensure_one()
        worked_data = self._get_attendance_summary()
        sales_records = self._get_sales_records()
        rules_bucket = {}
        categories = {}

        total_days = worked_data.get('total_days', 0.0)
        auto_leave = worked_data.get('leave_days', 0.0)
        applied_leave = self.leave_days if self.leave_days else auto_leave

        def sum_rules(*codes):
            flat_codes = self._flatten_codes(codes)
            return sum(rules_bucket.get(code, 0.0) for code in flat_codes)

        return {
            'env': self.env,
            'payslip': self,
            'employee': self.employee_id,
            'contract': self.contract_id,
            'worked_data': {
                'records': worked_data.get('records'),
                'total_hours': worked_data.get('total_hours', 0.0),
                'total_days': total_days,
                'leave_days': applied_leave,
            },
            'sales_records': sales_records,
            'inputs': {
                'sales_total': sum(sales_records.mapped('amount')),
                'products_sold': self.sales_products_count,
                'attendance_hours': worked_data.get('total_hours', 0.0),
                'attendance_records': worked_data.get('records'),
                'ot_normal_hours': self.ot_normal_hours,
                'ot_holiday_hours': self.ot_holiday_hours,
                'advance_amount': self.advance_amount,
                'penalty_amount': self.penalty_amount,
                'abc_rating': self.abc_rating or '',
            },
            'rules': rules_bucket,
            'categories': categories,
            'sum_rules': sum_rules,
            'result': 0.0,
            'result_qty': 1.0,
            'result_rate': 100.0,
        }

    @staticmethod
    def _flatten_codes(codes):
        flat = []
        for code in codes:
            if isinstance(code, (list, tuple, set)):
                flat.extend(code)
            else:
                flat.append(code)
        return flat

    def _get_attendance_summary(self):
        self.ensure_one()
        
        # Nếu chưa chọn nhân viên hoặc chưa có ngày từ/đến thì trả về mặc định
        if not self.employee_id or not self.date_from or not self.date_to:
            return {
                'records': self.env['hr.attendance'],
                'total_hours': 0.0,
                'total_days': 0.0,
                'leave_days': 0.0
            }

        # Chuyển ngày sang datetime để so sánh
        start_dt = fields.Datetime.to_datetime(fields.Date.to_string(self.date_from))
        end_dt = fields.Datetime.to_datetime(fields.Date.to_string(self.date_to)) + timedelta(days=1)

        # --- Lấy dữ liệu chấm công ---
        Attendance = self.env['hr.attendance'].sudo()
        attendances = Attendance.search([
            ('employee_id', '=', self.employee_id.id),
            ('check_in', '>=', start_dt),
            ('check_in', '<', end_dt),
        ])

        # Tổng giờ làm việc
        total_hours = sum(attendances.mapped('worked_hours'))

        # Số ngày có chấm công
        attendance_days = {
            fields.Datetime.to_datetime(rec.check_in).date() 
            for rec in attendances if rec.check_in
        }

        # --- Tính ngày nghỉ phép ---
        leave_days = 0.0
        Leave = self.env['forher.leave.request'].sudo()
        leaves = Leave.search([
            ('employee_id', '=', self.employee_id.id),
            ('state', 'in', ['approve', 'confirm']),
            ('start_date', '<=', self.date_to),
            ('end_date', '>=', self.date_from),
        ])

        for leave in leaves:
            start = max(leave.start_date, self.date_from)
            end = min(leave.end_date, self.date_to)
            leave_days += max((end - start).days + 1, 0)

        # --- Tính ngày nghỉ lễ (HOLIDAY) ---
        holiday_leaves = Leave.search([
            ('leave_type_id.code', '=', 'HOLIDAY'),
            ('start_date', '<=', self.date_to),
            ('end_date', '>=', self.date_from),
        ])

        for holiday in holiday_leaves:
            start = max(holiday.start_date, self.date_from)
            end = min(holiday.end_date, self.date_to)
            leave_days += max((end - start).days + 1, 0)

        # Trả về kết quả
        return {
            'records': attendances,
            'total_hours': total_hours,
            'total_days': float(len(attendance_days)),
            'leave_days': leave_days,
        }


    def _get_sales_records(self):
        self.ensure_one()
        SalesData = self.env['forher.payroll.sales.data']
        domain = [('employee_id', '=', self.employee_id.id)]
        if self.run_id:
            domain.append(('run_id', '=', self.run_id.id))
        else:
            if self.date_from:
                domain.append(('date', '>=', self.date_from))
            if self.date_to:
                domain.append(('date', '<=', self.date_to))
        return SalesData.search(domain)
