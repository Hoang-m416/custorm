from odoo import _, api, fields, models
from odoo.exceptions import UserError, ValidationError


class ForherPayslipRun(models.Model):
    _name = 'forher.payslip.run'
    _description = 'Kỳ tính lương Forher'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'date_start desc, id desc'

    name = fields.Char(default='New', readonly=True, copy=False, tracking=True)
    date_start = fields.Date(required=True, tracking=True)
    date_end = fields.Date(required=True, tracking=True)
    state = fields.Selection([
        ('draft', 'Nháp'),
        ('generated', 'Đã tạo phiếu nháp'),
        ('computed', 'Đã tính'),
        ('validated', 'Đã xác nhận'),
        ('done', 'Hoàn tất'),
        ('cancelled', 'Đã hủy'),
    ], default='draft', tracking=True)
    payslip_ids = fields.One2many('forher.payslip', 'run_id')
    payslip_count = fields.Integer(compute='_compute_payslip_count')
    company_id = fields.Many2one('res.company', required=True, default=lambda self: self.env.company)
    sales_data_ids = fields.One2many('forher.payroll.sales.data', 'run_id', string='Dữ liệu doanh số')

    _sql_constraints = [
        ('check_dates', 'CHECK(date_start <= date_end)', 'The start date must be before the end date.'),
    ]

    @api.model
    def create(self, vals):
        if vals.get('name') in (False, '/', 'New'):
            vals['name'] = self.env['ir.sequence'].next_by_code('forher.payslip.run') or 'New'
        if not vals.get('company_id'):
            vals['company_id'] = self.env.company.id
        return super().create(vals)

    @api.depends('payslip_ids')
    def _compute_payslip_count(self):
        for run in self:
            run.payslip_count = len(run.payslip_ids)

    @api.constrains('date_start', 'date_end')
    def _check_dates(self):
        for run in self:
            if run.date_start and run.date_end and run.date_start > run.date_end:
                raise ValidationError(_('Ngày kết thúc kỳ lương phải bằng hoặc sau ngày bắt đầu.'))

    def _get_contract_domain(self):
        self.ensure_one()
        domain = [
            ('state', 'in', ['open', 'waiting_approval']),
            ('salary_structure_id', '!=', False),
        ]
        if self.date_start:
            domain.append(('date_start', '<=', self.date_end or self.date_start))
        if self.date_start and self.date_end:
            domain.extend(['|', ('date_end', '=', False), ('date_end', '>=', self.date_start)])
        if self.company_id:
            domain.append(('company_id', '=', self.company_id.id))
        return domain

    def _prepare_payslip_vals(self, contract):
        self.ensure_one()
        return {
            'contract_id': contract.id,
            'employee_id': contract.employee_id.id,
            'structure_id': contract.salary_structure_id.id,
            'run_id': self.id,
            'date_from': self.date_start,
            'date_to': self.date_end,
            'company_id': contract.company_id.id or self.company_id.id,
        }

    def action_generate_payslips(self):
        Payslip = self.env['forher.payslip']
        Contract = self.env['forher.hr.contract']
        for run in self:
            if run.state not in ('draft', 'generated', 'cancelled'):
                raise UserError(_('Chỉ có thể tạo phiếu lương khi kỳ lương đang ở trạng thái nháp.'))
            if not run.date_start or not run.date_end:
                raise UserError(_('Vui lòng chọn thời gian kỳ lương trước khi tạo phiếu lương.'))

            contracts = Contract.search(run._get_contract_domain())
            if not contracts:
                raise UserError(_('Không tìm thấy hợp đồng nhân viên hợp lệ cho kỳ lương này.'))

            existing_contract_ids = set(run.payslip_ids.mapped('contract_id').ids)
            created_slips = Payslip
            for contract in contracts:
                if contract.id in existing_contract_ids:
                    continue
                created_slips += Payslip.create(run._prepare_payslip_vals(contract))

            if not (created_slips or run.payslip_ids):
                raise UserError(_('Không tạo được phiếu lương. Hãy đảm bảo mỗi hợp đồng có cấu trúc lương.'))

            if run.state in ('draft', 'cancelled'):
                run.state = 'generated'
        return True

    def action_compute(self):
        for run in self:
            if not run.payslip_ids:
                raise UserError(_('Không có phiếu lương để tính. Hãy tạo phiếu lương trước.'))
            run.payslip_ids.action_compute_sheet()
            run.state = 'computed'
        return True

    def action_validate(self):
        for run in self:
            if not run.payslip_ids:
                raise UserError(_('Không có phiếu lương để xác nhận.'))
            run.payslip_ids.action_confirm()
            run.state = 'validated'
        return True

    def action_done(self):
        for run in self:
            if not run.payslip_ids:
                raise UserError(_('Không có phiếu lương để đóng.'))
            run.payslip_ids.action_done()
            run.state = 'done'
        return True

    def action_cancel(self):
        for run in self:
            run.payslip_ids.action_cancel()
            run.state = 'cancelled'
        return True

    def action_reset_to_draft(self):
        for run in self:
            run.payslip_ids.action_reset_to_draft()
            run.state = 'draft'
        return True

    def action_view_payslips(self):
        self.ensure_one()
        action = self.env.ref('forher_payroll.forher_payroll_payslip_action').read()[0]
        action['domain'] = [('run_id', '=', self.id)]
        action['context'] = {'default_run_id': self.id}
        return action

    def action_open_import_wizard(self):
        self.ensure_one()
        return {
            'name': _('Nhập dữ liệu doanh số'),
            'type': 'ir.actions.act_window',
            'res_model': 'forher.payroll.import.wizard',
            'view_mode': 'form',
            'view_id': self.env.ref('forher_payroll.view_payroll_import_wizard').id,
            'target': 'new',
            'context': {'default_run_id': self.id},
        }
