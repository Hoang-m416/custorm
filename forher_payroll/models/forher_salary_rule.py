from odoo import _, api, fields, models
from odoo.exceptions import UserError
from odoo.tools.safe_eval import safe_eval


class ForherSalaryStructure(models.Model):
    _name = 'forher.salary.structure'
    _description = 'Cấu trúc lương Forher'
    _order = 'name'

    name = fields.Char(required=True)
    rule_ids = fields.One2many('forher.salary.rule', 'structure_id', string='Quy tắc lương')
    company_id = fields.Many2one('res.company', required=True, default=lambda self: self.env.company)
    active = fields.Boolean(default=True)
    note = fields.Text()


class ForherSalaryRule(models.Model):
    _name = 'forher.salary.rule'
    _description = 'Quy tắc lương Forher'
    _order = 'sequence, id'

    name = fields.Char(required=True)
    code = fields.Char(required=True)
    sequence = fields.Integer(default=10)
    structure_id = fields.Many2one('forher.salary.structure', required=True, ondelete='cascade')
    rule_type = fields.Selection([
        ('basic', 'Basic'),
        ('allowance', 'Allowance'),
        ('deduction', 'Deduction'),
        ('other', 'Other'),
    ], required=True, default='other')
    amount_python_compute = fields.Text(
        string='Mã Python',
        default='result = 0.0',
        required=True,
        help='Viết đoạn mã Python gán số tiền tính được cho biến result.'
    )
    always_include = fields.Boolean(
        string='Luôn hiển thị trên phiếu lương',
        help='Giữ dòng này trên phiếu lương ngay cả khi số tiền bằng 0.'
    )
    description = fields.Text()
    company_id = fields.Many2one('res.company', related='structure_id.company_id', store=True, readonly=True)

    _sql_constraints = [
        ('code_structure_unique', 'unique(code, structure_id)', 'Mã quy tắc lương phải là duy nhất trong mỗi cấu trúc.'),
    ]

    @api.model
    def create(self, vals):
        if vals.get('code'):
            vals['code'] = vals['code'].strip().upper()
        return super().create(vals)

    def write(self, vals):
        if vals.get('code'):
            vals['code'] = vals['code'].strip().upper()
        return super().write(vals)

    def _compute_rule_amount(self, localdict):
        self.ensure_one()
        safe_locals = dict(localdict)
        safe_locals.setdefault('result', 0.0)
        safe_locals.setdefault('result_qty', safe_locals.get('quantity', 1.0))
        safe_locals.setdefault('result_rate', safe_locals.get('rate', 100.0))
        try:
            safe_eval(self.amount_python_compute or 'result = 0.0', safe_locals, mode='exec', nocopy=True)
        except Exception as exc:
            raise UserError(
                _(
                    'Python code execution failed for salary rule %(rule)s:\n%(error)s',
                    rule=self.display_name,
                    error=exc,
                )
            ) from exc

        amount = safe_locals.get('result', 0.0)
        quantity = safe_locals.get('result_qty', safe_locals.get('quantity', 1.0))
        rate = safe_locals.get('result_rate', safe_locals.get('rate', 100.0))
        skip_line = safe_locals.get('skip_line', False)

        return amount, quantity, rate, skip_line



