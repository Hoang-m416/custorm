from odoo import models, fields, api

class EmployeeType(models.Model):
    _name = 'employee.type'
    _description = 'Loại nhân viên'

    name = fields.Char('Tên loại nhân viên', required=True)
    code = fields.Char('Mã', required=True)

    # Quan hệ với nhân viên
    employee_ids = fields.One2many('hr.employee', 'employee_type_id', string='Nhân viên')
    employee_count = fields.Integer(string='Số lượng nhân viên', compute='_compute_employee_count')

    @api.depends('employee_ids')
    def _compute_employee_count(self):
        for rec in self:
            rec.employee_count = len(rec.employee_ids)

    def action_view_employees(self):
        return {
            'name': 'Nhân viên',
            'type': 'ir.actions.act_window',
            'res_model': 'hr.employee',
            'view_mode': 'list,form',
            'domain': [('employee_type_id', '=', self.id)],
            'context': {'default_employee_type_id': self.id}
        }
