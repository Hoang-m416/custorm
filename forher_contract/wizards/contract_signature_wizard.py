from odoo import fields, models, api


class ContractSignatureWizard(models.TransientModel):
    _name = 'contract.signature.wizard'
    _description = 'Contract Signature Wizard'

    name = fields.Char()
    contract_forher_id = fields.Many2one(
        'forher.hr.contract', string='Contract'
    )
    signature = fields.Binary(string='Signature', readonly=False)

    def action_signature(self):
        for record in self:
            if record.contract_forher_id:
                record.contract_forher_id.contract_signature = record.signature
