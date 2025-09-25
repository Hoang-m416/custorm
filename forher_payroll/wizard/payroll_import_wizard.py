import base64
import csv
import io
import logging

from odoo import _, fields, models
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)


class PayrollImportWizard(models.TransientModel):
    _name = 'forher.payroll.import.wizard'
    _description = 'Trợ lý nhập dữ liệu lương Forher'

    run_id = fields.Many2one('forher.payslip.run', string='Kỳ lương', required=True)
    data_file = fields.Binary(string='Tệp CSV', required=True)
    filename = fields.Char(string='Tên tệp')
    delimiter = fields.Char(string='Ký tự phân tách', default=',')

    def action_import(self):
        self.ensure_one()
        if not self.data_file:
            raise UserError(_('Vui lòng tải lên tệp CSV để nhập dữ liệu.'))

        decoded = base64.b64decode(self.data_file)
        try:
            text = decoded.decode('utf-8-sig')
        except UnicodeDecodeError:
            text = decoded.decode('utf-8')

        delimiter = (self.delimiter or ',').strip() or ','
        reader = csv.DictReader(io.StringIO(text), delimiter=delimiter)
        if not reader.fieldnames:
            raise UserError(_('Tệp được cung cấp không có dòng tiêu đề để ánh xạ các trường.'))

        Employee = self.env['hr.employee'].sudo()
        SalesData = self.env['forher.payroll.sales.data'].sudo()

        missing_codes = []
        created = 0
        for row in reader:
            employee_code = (row.get('employee_code') or row.get('code') or row.get('employee'))
            employee_code = employee_code.strip() if employee_code else False
            if not employee_code:
                _logger.debug('Bỏ qua dòng thiếu mã nhân viên: %s', row)
                continue

            employee = Employee.search([('employee_code', '=', employee_code)], limit=1)
            if not employee:
                missing_codes.append(employee_code)
                continue

            amount_raw = (row.get('amount') or row.get('value') or row.get('total') or '0').strip()
            try:
                amount = float(amount_raw)
            except ValueError:
                _logger.warning('Giá trị %s không hợp lệ cho nhân viên %s. Mặc định 0.', amount_raw, employee_code)
                amount = 0.0

            products_raw = row.get('products_sold') or row.get('qty') or row.get('quantity') or 0
            try:
                products_sold = int(float(str(products_raw).strip() or '0'))
            except ValueError:
                products_sold = 0

            SalesData.create({
                'run_id': self.run_id.id,
                'employee_id': employee.id,
                'amount': amount,
                'products_sold': products_sold,
                'reference': (row.get('reference') or row.get('ref') or '').strip() or False,
                'note': (row.get('note') or row.get('description') or '').strip() or False,
                'date': self.run_id.date_end,
            })
            created += 1

        message = _('Đã nhập %s dòng doanh số.', created)
        notification_type = 'success'
        if missing_codes:
            message += _(' Thiếu nhân viên với các mã: %s.', ', '.join(sorted(set(missing_codes))))
            notification_type = 'warning'

        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _('Nhập dữ liệu doanh số'),
                'message': message,
                'type': notification_type,
                'sticky': False,
            }
        }
