from odoo import fields, models, api


class ForherContract(models.Model):
    _inherit = 'forher.hr.contract'

    position_allowance = fields.Monetary(
        string='Position Allowance',
        currency_field='company_currency_id',
        help='Allowance amount for the position, applied when computing payroll.'
    )
    job_allowance = fields.Monetary(
    string='Job Allowance',
    currency_field='company_currency_id',
    compute='_compute_job_allowance',
    store=True,
    help='Allowance amount for specific job responsibilities.'
)

    @api.depends('total_allowance')
    def _compute_job_allowance(self):
        for contract in self:
            contract.job_allowance = contract.total_allowance

    company_currency_id = fields.Many2one('res.currency', related='company_id.currency_id', readonly=True)

    salary_structure_id = fields.Many2one(
        'forher.salary.structure',
        string='Salary Structure',
        tracking=True,
        help='Select the salary structure used to compute payslips for this contract.'
    )
