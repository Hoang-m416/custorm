from odoo import api, fields, models


class ForherPayrollSalesData(models.Model):
    _name = 'forher.payroll.sales.data'
    _description = 'Dữ liệu doanh số Forher'
    _order = 'run_id, employee_id, id'

    run_id = fields.Many2one('forher.payslip.run', string='Kỳ lương', required=True, ondelete='cascade')
    employee_id = fields.Many2one('hr.employee', string='Nhân viên', required=True)
    amount = fields.Monetary(currency_field='currency_id', string='Số tiền', required=True)
    currency_id = fields.Many2one('res.currency', required=True, default=lambda self: self.env.company.currency_id)
    date = fields.Date(string='Ngày', default=fields.Date.context_today)
    reference = fields.Char(string='Tham chiếu')
    note = fields.Char(string='Ghi chú')
    company_id = fields.Many2one('res.company', related='run_id.company_id', store=True, readonly=True)
    products_sold = fields.Integer(string='Số lượng sản phẩm', default=0)

    @api.model
    def get_total_for_employee(self, run, employee):
        if not run or not employee:
            return 0.0
        run_id = run.id if isinstance(run, models.BaseModel) else run
        employee_id = employee.id if isinstance(employee, models.BaseModel) else employee
        records = self.search([
            ('run_id', '=', run_id),
            ('employee_id', '=', employee_id),
        ])
        return sum(records.mapped('amount'))
