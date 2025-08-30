from odoo import models, fields, api, _
from odoo.exceptions import ValidationError, AccessDenied
import re

class ResUsers(models.Model):
    _inherit = 'res.users'

    plain_password = fields.Char(
        string="Mật khẩu",
        store=False,  # Không lưu vào DB
        help="Nhập mật khẩu khi tạo User (sẽ được hash tự động)."
    )

    def _validate_password_strength(self, password):
        if len(password) < 8:
            raise ValidationError(_("Mật khẩu phải có ít nhất 8 ký tự."))
        if not re.search(r"[A-Za-z]", password) or not re.search(r"\d", password):
            raise ValidationError(_("Mật khẩu phải bao gồm cả chữ cái và số."))

    @api.model
    def create(self, vals):
        if vals.get('plain_password'):
            self._validate_password_strength(vals['plain_password'])
            vals['password'] = vals.pop('plain_password')
        return super().create(vals)

    def write(self, vals):
        if vals.get('plain_password'):
            self._validate_password_strength(vals['plain_password'])
            vals['password'] = vals.pop('plain_password')
        return super().write(vals)

    # Kiểm tra trạng thái khi đăng nhập
    def check_credentials(self, password):
        res = super().check_credentials(password)  # Kiểm tra password trước

        # Lấy nhân viên của người dùng
        emp = self.env['hr.employee'].search([('user_id', '=', self.id)], limit=1)

        # Nếu nhân viên tồn tại, kiểm tra trạng thái
        if emp:
            if emp.state == 'suspended':
                raise AccessDenied(_("Tài khoản của bạn đang bị tạm ngưng. Không thể đăng nhập."))
            elif emp.state == 'resigned':
                raise AccessDenied(_("Nhân viên này đã nghỉ việc. Không thể đăng nhập."))
        
        return res
