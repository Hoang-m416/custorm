from odoo import models, fields

class CompanyOverview(models.Model):
    _name = 'forher.company.overview'
    _description = 'Tổng quan công ty'
    _inherit = ['mail.thread', 'mail.activity.mixin']

    # Công ty mẹ (Forher) - liên kết trực tiếp tới res.company
    company_id = fields.Many2one('res.company', string='Công ty mẹ', required=True)

    # Lĩnh vực kinh doanh
    business_field = fields.Char('Lĩnh vực kinh doanh', default='Thời trang công sở và áo dài')

    # Lấy danh sách chi nhánh (child_ids của res.company)
    subcompany_ids = fields.One2many(related='company_id.child_ids', string='Chi nhánh', readonly=True)

    # Cấp phân quyền
    permission_level_ids = fields.One2many(
        'forher.permission.level',
        'company_overview_id',
        string='Cấp phân quyền'
    )


class PermissionLevel(models.Model):
    _name = 'forher.permission.level'
    _description = 'Cấp phân quyền Forher'
    _inherit = ['mail.thread', 'mail.activity.mixin']

    name = fields.Char('Tên cấp', required=True)
    code = fields.Selection([
        ('board', 'Ban Giám Đốc'),
        ('branch_manager', 'Quản lý Chi nhánh'),
        ('accountant', 'Kế toán'),
        ('employee', 'Nhân viên'),
    ], string='Mã cấp', required=True)
    description = fields.Text('Mô tả')

    company_overview_id = fields.Many2one(
        'forher.company.overview',
        string='Công ty mẹ'
    )
