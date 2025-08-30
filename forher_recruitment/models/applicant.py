from odoo import models, fields, api, _
from odoo.exceptions import UserError
from datetime import timedelta


class Applicant(models.Model):
    _name = "forher.applicant"
    _description = "Ứng viên"
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = "create_date desc"

    # --- Basic Info ---
    name = fields.Char("Họ tên", required=True, tracking=True)
    email = fields.Char("Email", tracking=True)
    phone = fields.Char("SĐT", tracking=True)
    request_id = fields.Many2one('recruitment.request', string="Yêu cầu tuyển dụng", tracking=True)
    position_applied = fields.Char("Vị trí ứng tuyển", tracking=True)

    # --- Thông tin công ty từ request ---
    company_id = fields.Many2one(
        'res.company',
        string="Công ty",
        related='request_id.company_id',
        store=True,
        readonly=True,
        tracking=True
    )

    resume = fields.Binary("CV / Resume")
    resume_filename = fields.Char("Tên file CV")

    # --- Workflow ---
    state = fields.Selection([
        ('new', 'Mới'),
        ('screened', 'Sàng lọc'),
        ('interview_scheduled', 'Đã lên lịch PV'),
        ('interviewing', 'Đang phỏng vấn'),
        ('interview_passed', 'Đậu phỏng vấn'),
        ('offer', 'Offer'),
        ('pending_confirmation', 'Chờ xác nhận'),
        ('direct_hire', 'Tuyển ngay'),
        ('hire_confirmed', 'Đã xác nhận tuyển'),
        ('hired', 'Đã tuyển'),
        ('waiting', 'Dự bị'),
        ('rejected', 'Từ chối')
    ], default='new', string="Trạng thái", tracking=True)

    # --- Computed Fields ---
    progress = fields.Float("Tiến trình (%)", compute="_compute_progress", store=True)
    state_label = fields.Char("Trạng thái hiển thị", compute="_compute_state_label", store=True)

    # --- Override create ---
    @api.model
    def create(self, vals):
        record = super().create(vals)
        if record.request_id and record.request_id.number_of_positions > 0:
            hired_count = self.env['forher.applicant'].sudo().search_count([
                ('request_id', '=', record.request_id.id),
                ('state', '=', 'hired')
            ])
            if hired_count >= record.request_id.number_of_positions:
                record.state = 'waiting'
                record.message_post(body=_("Ứng viên này đã được đưa vào danh sách Dự bị do số lượng đã đủ."))
        return record

    # --- Actions ---
    def action_screen(self):
        for rec in self:
            if rec.state != 'new':
                continue
            rec.state = 'screened'
            rec.message_post(body=_("Ứng viên đã được sàng lọc."))

    def action_schedule_interview(self):
        for rec in self:
            if rec.state != 'screened':
                raise UserError(_("Chỉ ứng viên đã sàng lọc mới có thể lên lịch phỏng vấn."))

            # Tạo lịch calendar
            event = self.env['calendar.event'].create({
                'name': _("Phỏng vấn: %s") % rec.name,
                'start': fields.Datetime.now() + timedelta(days=1),
                'stop': fields.Datetime.now() + timedelta(days=1, hours=1),
                'allday': False,
                'description': _("Phỏng vấn ứng viên: %s\nVị trí: %s") %
                                (rec.name, rec.position_applied or ''),
                'partner_ids': [(4, self.env.user.partner_id.id)],
            })

            # Lấy hr.employee của user hiện tại
            interviewer_emp = self.env['hr.employee'].search([('user_id', '=', self.env.user.id)], limit=1)
            if not interviewer_emp:
                raise UserError(_("Người phỏng vấn chưa được đăng ký nhân viên."))

            # Tạo record forher.interview
            interview = self.env['forher.interview'].create({
                'applicant_id': rec.id,
                'interview_date': event.start,
                'interviewer_id': interviewer_emp.id,
                'location': 'Văn phòng chính',
                'notes': 'Tạo tự động khi lên lịch phỏng vấn',
            })

            rec.state = 'interview_scheduled'
            rec.message_post(body=_("Ứng viên đã được lên lịch phỏng vấn: %s") % event.name)

            return {
                'name': _('Phỏng vấn'),
                'type': 'ir.actions.act_window',
                'res_model': 'forher.interview',
                'view_mode': 'form',
                'res_id': interview.id,
                'target': 'current',
            }

    def action_send_offer(self):
        for rec in self:
            if rec.state != 'interview_passed':
                raise UserError(_("Chỉ ứng viên đã đậu phỏng vấn mới có thể gửi offer."))

            offer_letter = self.env['forher.offer.letter'].create({
                'applicant_id': rec.id,
                'state': 'draft',
                'confirm_token': self.env['ir.sequence'].next_by_code('forher.offer.token') or str(rec.id),
            })

            template = self.env.ref('forher_recruitment.email_template_offer_letter', raise_if_not_found=False)
            if not template:
                raise UserError(_("Không tìm thấy mẫu email offer."))

            template.sudo().send_mail(offer_letter.id, force_send=True)

            rec.state = 'pending_confirmation'
            rec.message_post(body=_("Đã gửi offer đến ứng viên, đang chờ xác nhận."))

    def action_reject(self):
        for rec in self:
            if rec.state == 'hired':
                raise UserError(_("Không thể từ chối ứng viên đã tuyển."))
            rec.state = 'rejected'
            rec.message_post(body=_("Ứng viên đã bị từ chối."))

    def action_confirm_hire(self):
        for rec in self:
            if rec.state != 'interview_passed':
                raise UserError(_("Chỉ ứng viên đã đậu phỏng vấn mới có thể xác nhận tuyển."))
            rec.state = 'hire_confirmed'
            rec.message_post(body=_("Ứng viên đã được xác nhận tuyển sau phỏng vấn."))

    def action_hire(self):
        for rec in self:
            if rec.state != 'hire_confirmed':
                raise UserError(_("Chỉ ứng viên đã được xác nhận tuyển mới có thể tạo nhân viên."))

            # Map position sang hr.job
            job_id = False
            if rec.request_id and rec.request_id.position:
                job_name = rec.request_id.position
                job = self.env['hr.job'].sudo().search([('name', '=', job_name)], limit=1)
                if not job:
                    job = self.env['hr.job'].sudo().create({'name': job_name})
                job_id = job.id

            # Lấy hoặc tạo hr.department theo tên công ty
            department_id = False
            if rec.company_id:
                department = self.env['hr.department'].sudo().search([('name', '=', rec.company_id.name)], limit=1)
                if not department:
                    department = self.env['hr.department'].sudo().create({'name': rec.company_id.name})
                department_id = department.id

            # --- Tạo email công ty ---
            company_domain = "forher.com"

            def normalize_name(name):
                import unicodedata
                name = name.lower().strip()
                name = unicodedata.normalize('NFD', name)
                name = ''.join(c for c in name if unicodedata.category(c) != 'Mn')  # bỏ dấu
                name = name.replace(' ', '.').replace('..', '.')
                return ''.join(c for c in name if c.isalnum() or c == '.')

            base_email = normalize_name(rec.name)
            email_candidate = f"{base_email}@{company_domain}"

            existing_emails = self.env['hr.employee'].sudo().search([('work_email', 'ilike', f"%@{company_domain}")])
            emails = existing_emails.mapped('work_email')

            counter = 1
            while email_candidate in emails:
                counter += 1
                email_candidate = f"{base_email}{counter}@{company_domain}"

            employee_vals = {
                'name': rec.name,
                'work_email': email_candidate,
                'work_phone': rec.phone,
                'job_id': job_id,
                'company_id': rec.company_id.id if rec.company_id else False,
                'department_id': department_id,
            }
            self.env['hr.employee'].sudo().create(employee_vals)

            rec.state = 'hired'
            rec.message_post(body=_("Ứng viên đã được tuyển và tạo nhân viên với email: %s") % email_candidate)

            if rec.request_id:
                rec.request_id.update_state_based_on_positions()

    def action_delete_waiting(self):
        for rec in self:
            if rec.state != 'waiting':
                raise UserError(_("Chỉ có thể xóa ứng viên ở trạng thái Dự bị."))
            rec.unlink()

    # Thêm trường màu
    progress_color = fields.Char("Màu tiến trình", compute="_compute_progress_color", store=True)

    @api.depends('state')
    def _compute_progress_color(self):
        color_map = {
            'new': 'blue',
            'screened': 'orange',
            'interview_scheduled': 'purple',
            'interviewing': 'teal',
            'interview_passed': 'green',
            'hire_confirmed': 'primary',
            'offer': 'darkblue',
            'hired': 'success',
            'waiting': 'warning',
            'rejected': 'danger'
        }
        for rec in self:
            rec.progress_color = color_map.get(rec.state, 'info')

    @api.depends('state')
    def _compute_progress(self):
        progress_map = {
            'new': 10,
            'screened': 25,
            'interview_scheduled': 40,
            'interviewing': 55,
            'interview_passed': 70,
            'offer': 80,
            'pending_confirmation': 85,
            'direct_hire': 90,
            'hired': 100,
            'waiting': 60,
            'rejected': 0
        }
        for rec in self:
            rec.progress = progress_map.get(rec.state, 0)

    @api.depends('state')
    def _compute_state_label(self):
        label_map = {
            'new': 'Mới',
            'screened': 'Sàng lọc',
            'interview_scheduled': 'Đã lên lịch PV',
            'interviewing': 'Đang phỏng vấn',
            'interview_passed': 'Đậu phỏng vấn',
            'offer': 'Offer',
            'pending_confirmation': 'Chờ xác nhận',
            'hire_confirmed': 'Đã xác nhận tuyển',
            'direct_hire': 'Tuyển ngay',
            'hired': 'Đã tuyển',
            'waiting': 'Dự bị',
            'rejected': 'Từ chối'
        }
        for rec in self:
            rec.state_label = label_map.get(rec.state, '')


class ApplicantWizard(models.TransientModel):
    _name = "forher.applicant.wizard"
    _description = "Wizard Tạo Ứng viên"

    name = fields.Char("Họ tên", required=True)
    email = fields.Char("Email")
    phone = fields.Char("SĐT")
    position_applied = fields.Char("Vị trí ứng tuyển")
    request_id = fields.Many2one('recruitment.request', string="Yêu cầu tuyển dụng")
    resume = fields.Binary("CV / Resume")
    resume_filename = fields.Char("Tên file CV")

    def action_save_draft(self):
        for rec in self:
            self.env['forher.applicant'].create({
                'name': rec.name,
                'email': rec.email,
                'phone': rec.phone,
                'position_applied': rec.position_applied,
                'request_id': rec.request_id.id if rec.request_id else False,
                'resume': rec.resume,
                'resume_filename': rec.resume_filename,
                'state': 'new',
            })
        return {'type': 'ir.actions.act_window_close'}

    def action_submit(self):
        for rec in self:
            applicant = self.env['forher.applicant'].create({
                'name': rec.name,
                'email': rec.email,
                'phone': rec.phone,
                'position_applied': rec.position_applied,
                'request_id': rec.request_id.id if rec.request_id else False,
                'resume': rec.resume,
                'resume_filename': rec.resume_filename,
                'state': 'new',
            })
            applicant.message_post(body=_("Ứng viên được tạo từ wizard."))
        return {'type': 'ir.actions.act_window_close'}
