from odoo import fields, models


class HrEmployee(models.Model):
    _inherit = 'hr.employee'

    dependent_count = fields.Integer(string='Number of dependents', default=0, help='Used to compute personal income tax deductions.')
    position_allowance = fields.Monetary(string='Default position allowance', currency_field='company_currency_id', help='Fallback value when the contract does not define a position allowance.')
    job_allowance = fields.Monetary(string='Default job allowance', currency_field='company_currency_id', help='Fallback value when the contract does not define a job allowance.')
    company_currency_id = fields.Many2one('res.currency', string='Currency', related='company_id.currency_id', readonly=True)
