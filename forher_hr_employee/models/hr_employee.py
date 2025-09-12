from odoo import models, fields, api
from odoo.exceptions import ValidationError
from datetime import date

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

    # Liên kết với ForHer Contract
    forher_contract_ids = fields.One2many(
        'forher.hr.contract',
        'employee_id',
        string='Hợp đồng ForHer'
    )
    forher_contract_id = fields.Many2one(
        'forher.hr.contract',
        string='Hợp đồng hiện tại (ForHer)',
        compute='_compute_current_forher_contract',
        store=True
    )
    current_forher_contract_id = fields.Many2one(
        'forher.hr.contract',
        string='Hợp đồng hiện tại',
        compute='_compute_current_forher_contract',
        store=True
    )

    @api.depends('forher_contract_ids', 'forher_contract_ids.state')
    def _compute_current_forher_contract(self):
        for emp in self:
            contracts = emp.forher_contract_ids.filtered(lambda c: c.state in ['open', 'waiting_approval'])
            emp.current_forher_contract_id = contracts[:1] if contracts else False
            emp.forher_contract_id = emp.current_forher_contract_id

    # Thông tin ngân hàng
    bank_account = fields.Char('Tài khoản ngân hàng')
    bank_name = fields.Char('Ngân hàng')

    # Cấp quyền kế thừa từ overview
    permission_level_id = fields.Many2one('forher.permission.level', 'Cấp phân quyền')

    # Hồ sơ nhân viên
    hr_employee_document_ids = fields.One2many(
        'hr.employee.document',
        'employee_id',
        string='Hồ sơ nhân viên'
    )

    # Học vấn & kinh nghiệm
    education_level = fields.Selection([
        ('highschool','Trung học'),
        ('college','Cao đẳng'),
        ('university','Đại học'),
        ('master','Thạc sĩ'),
        ('phd','Tiến sĩ'),
    ], 'Trình độ học vấn')
    experience_years = fields.Integer('Kinh nghiệm (năm)')
    seniority_years = fields.Integer('Thâm niên (năm)', compute='_compute_seniority', store=True)

    @api.depends('forher_contract_ids.date_start')
    def _compute_seniority(self):
        for emp in self:
            if emp.forher_contract_ids:
                start_date = min(emp.forher_contract_ids.mapped('date_start'))
                if start_date:
                    emp.seniority_years = (fields.Date.today() - start_date).days // 365
                else:
                    emp.seniority_years = 0
            else:
                emp.seniority_years = 0

    # Khen thưởng & kỷ luật
    reward_ids = fields.One2many('hr.employee.reward', 'employee_id', string='Khen thưởng - Kỷ luật')

    # Lịch sử nâng lương
    salary_increase_ids = fields.One2many('hr.salary.increase', 'employee_id', string='Lịch sử nâng lương')

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

    @api.onchange('file')
    def _onchange_file(self):
        if self.file and not self.filename:
            self.filename = "Uploaded_file"


# ================= HR Employee Reward / Discipline =================
class HrEmployeeReward(models.Model):
    _name = 'hr.employee.reward'
    _description = 'Khen thưởng - Kỷ luật'
    _inherit = ['mail.thread', 'mail.activity.mixin']

    employee_id = fields.Many2one('hr.employee', string='Nhân viên', required=True, ondelete='cascade')
    reward_type = fields.Selection([
        ('reward','Khen thưởng'),
        ('discipline','Kỷ luật')
    ], 'Loại', required=True)
    description = fields.Text('Nội dung')
    date = fields.Date('Ngày', default=fields.Date.today)
    value = fields.Float('Giá trị thưởng/phạt (VNĐ)')
    note = fields.Char('Ghi chú')


# ================= HR Salary Increase =================
class HrSalaryIncrease(models.Model):
    _name = 'hr.salary.increase'
    _description = 'Xét duyệt nâng lương'
    _inherit = ['mail.thread', 'mail.activity.mixin']

    employee_id = fields.Many2one('hr.employee', string='Nhân viên', required=True, ondelete='cascade')
    old_salary = fields.Float('Mức lương cũ')
    new_salary = fields.Float('Mức lương mới')
    reason = fields.Text('Lý do')
    criteria = fields.Selection([
        ('seniority','Thâm niên'),
        ('performance','Thành tích'),
        ('ability','Năng lực')
    ], 'Tiêu chí chính')
    date = fields.Date('Ngày xét duyệt', default=fields.Date.today)
    approved_by = fields.Many2one('hr.employee', string='Người duyệt')


# ================= Compute số nhân viên trên Company =================
class ResCompany(models.Model):
    _inherit = 'res.company'

    manager_id = fields.Many2one(
        'hr.employee',
        string='Người quản lý',
        compute='_compute_manager_id',
        store=True
    )
    employee_ids = fields.One2many(
        'hr.employee', 'company_id', string='Nhân viên'
    )
    employee_count = fields.Integer(
        'Nhân viên',
        compute='_compute_employee_count'
    )

    @api.depends('employee_ids', 'employee_ids.position')
    def _compute_manager_id(self):
        for company in self:
            manager = company.employee_ids.filtered(lambda e: e.position == 'manager')
            company.manager_id = manager[:1].id if manager else False

    def _compute_employee_count(self):
        for company in self:
            company.employee_count = len(company.employee_ids)

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
