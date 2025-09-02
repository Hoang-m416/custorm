from odoo import fields, models, api


class HrEmployee(models.Model):
    _inherit = 'hr.employee'

    forher_contract_id = fields.Many2one(
        'forher.hr.contract', string='Contract'
    )

    
