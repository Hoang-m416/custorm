from odoo import models, fields, api
from odoo.exceptions import ValidationError

# ================= HR Employee =================
class HrEmployee(models.Model):
    _inherit = 'hr.employee'

    # ================= Mã nhân viên tự động =================
    employee_code = fields.Char('Mã nhân viên', readonly=True, copy=False, default='New')

    # Thông tin cá nhân
    dob = fields.Date('Ngày sinh')
    gender = fields.Selection([('male','Nam'),('female','Nữ'),('other','Khác')], 'Giới tính')
    identity_id = fields.Char('CMND/CCCD')
    address = fields.Char('Địa chỉ')
    work_phone = fields.Char('Số điện thoại')
    email_personal = fields.Char('Email cá nhân')
    employee_type_id = fields.Many2one('employee.type', string='Loại nhân viên')

    # Thông tin công việc
    job_title = fields.Char('Chức danh')
    company_id = fields.Many2one('res.company', string='Chi nhánh')

    # Chức vụ
    position = fields.Selection([
        ('director','Giám đốc'),
        ('manager','Quản lý'),
        ('employee','Nhân viên')
    ], string='Chức vụ', default='employee')

    # Trạng thái nhân viên
    state = fields.Selection([
        ('active','Hoạt động'),
        ('suspended','Tạm ngưng'),
        ('resigned','Nghỉ việc')
    ], string='Trạng thái nhân viên', default='active', tracking=True)

    # Field ảo xác định vị trí người dùng đăng nhập
    current_user_position = fields.Selection([
        ('director','Giám đốc'),
        ('manager','Quản lý'),
        ('employee','Nhân viên')
    ], string='Vị trí hiện tại', compute='_compute_current_user_position')

    @api.depends('user_id')
    def _compute_current_user_position(self):
        for rec in self:
            user = self.env.user
            emp = self.env['hr.employee'].search([('user_id','=',user.id)], limit=1)
            rec.current_user_position = emp.position if emp else False

    # Thông tin hợp đồng
    contract_type = fields.Selection([
        ('full_time','Full-time'),
        ('part_time','Part-time'),
        ('temporary','Temporary')
    ], 'Loại hợp đồng')
    contract_start = fields.Date('Ngày bắt đầu')
    contract_end = fields.Date('Ngày kết thúc')
    salary = fields.Float('Mức lương')

    # Thông tin ngân hàng
    bank_account = fields.Char('Tài khoản ngân hàng')
    bank_name = fields.Char('Ngân hàng')

    # Cấp quyền kế thừa từ overview
    permission_level_id = fields.Many2one('forher.permission.level', 'Cấp phân quyền')

    # Hồ sơ nhân viên (cập nhật bởi admin hoặc nhân viên)
    hr_employee_document_ids = fields.One2many(
        'hr.employee.document',
        'employee_id',
        string='Hồ sơ nhân viên'
    )

    # ================= Kiểm tra các field bắt buộc =================
    @api.constrains('work_phone')
    def _check_required_personal_bank_fields(self):
        for rec in self:
            missing_fields = []
            for field_name, label in [
                ('work_phone','Số điện thoại'),
            ]:
                if not getattr(rec, field_name):
                    missing_fields.append(label)
            if missing_fields:
                message = "<b>Vui lòng điền đầy đủ các thông tin trước khi lưu:</b><br/>"
                for field_label in missing_fields:
                    message += f"<span style='color:red;'>❌ {field_label}</span><br/>"
                raise ValidationError(message)

    # ================= Hàm chuyển trạng thái =================
    def action_set_active(self):
        self.state = 'active'

    def action_set_suspended(self):
        self.state = 'suspended'

    def action_set_resigned(self):
        self.state = 'resigned'

    # ================= Ghi đè create để sinh mã nhân viên tự động =================
    @api.model
    def create(self, vals):
        if vals.get('employee_code', 'New') == 'New':
            last_employee = self.env['hr.employee'].search([], order='id desc', limit=1)
            if last_employee and last_employee.employee_code:
                try:
                    last_number = int(last_employee.employee_code.replace('.FH',''))
                except:
                    last_number = 0
            else:
                last_number = 0
            vals['employee_code'] = f'.FH{last_number + 1}'
        return super(HrEmployee, self).create(vals)


# ================= HR Employee Document =================
class HrEmployeeDocument(models.Model):
    _name = 'hr.employee.document'
    _description = 'Hồ sơ nhân viên'
    _inherit = ['mail.thread', 'mail.activity.mixin']

    name = fields.Char('Tên hồ sơ', required=True)
    employee_id = fields.Many2one('hr.employee', string='Nhân viên', required=True, ondelete='cascade')
    file = fields.Binary('File', required=True)
    filename = fields.Char('Tên file')
    document_type = fields.Selection([
        ('identity', 'CMND/CCCD'),
        ('contract', 'Hợp đồng'),
        ('certificate', 'Chứng chỉ'),
        ('other', 'Khác')
    ], 'Loại hồ sơ', default='other')
    upload_date = fields.Datetime('Ngày tải lên', default=fields.Datetime.now)

    # ================= Tự động lấy tên file khi upload =================
    @api.onchange('file')
    def _onchange_file(self):
        if self.file and not self.filename:
            self.filename = "Uploaded_file"


# ================= Compute số nhân viên trên Company =================
class ResCompany(models.Model):
    _inherit = 'res.company'

    # Người quản lý của chi nhánh
    manager_id = fields.Many2one(
        'hr.employee',
        string='Người quản lý',
        compute='_compute_manager_id',
        store=True
    )

    # Danh sách nhân viên thuộc chi nhánh
    employee_ids = fields.One2many(
        'hr.employee', 'company_id', string='Nhân viên'
    )

    # Số lượng nhân viên
    employee_count = fields.Integer(
        'Nhân viên',
        compute='_compute_employee_count'
    )

    # Compute manager_id dựa vào trường selection 'r' trong hr.employee
    @api.depends('employee_ids', 'employee_ids.r')
    def _compute_manager_id(self):
        for company in self:
            manager = company.employee_ids.filtered(lambda e: e.r == 'manager')
            company.manager_id = manager[:1].id if manager else False

    # Compute số lượng nhân viên
    def _compute_employee_count(self):
        for company in self:
            company.employee_count = len(company.employee_ids)

    # Action xem danh sách nhân viên
    def action_view_employees(self):
        self.ensure_one()
        return {
            'name': f'Nhân viên - {self.name}',
            'type': 'ir.actions.act_window',
            'res_model': 'hr.employee',
            'view_mode': 'kanban,form',
            'domain': [('company_id', '=', self.id)],
            'context': {'default_company_id': self.id},
        }