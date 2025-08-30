from odoo import models, fields, api, _
import uuid

class OfferLetter(models.Model):
    _name = "forher.offer.letter"
    _description = "Offer Letter"
    _inherit = ['mail.thread', 'mail.activity.mixin']

    applicant_id = fields.Many2one(
        'forher.applicant',
        string="Ứng viên",
        required=True,
        domain="[('state', 'in', ('interview_passed','pending_confirmation'))]",
        tracking=True
    )
    name = fields.Char("Họ tên", related="applicant_id.name", store=True)
    position = fields.Char("Vị trí", related="applicant_id.position_applied", store=True)
    email = fields.Char("Email", related="applicant_id.email", store=True)
    phone = fields.Char("SĐT", related="applicant_id.phone", store=True)
    notes = fields.Text("Ghi chú")

    confirm_token = fields.Char("Offer Token", readonly=True)
    state_label = fields.Char(string="Nhãn trạng thái", compute="_compute_state_label", store=True)

    state = fields.Selection([
        ('draft', 'Nháp'),
        ('sent', 'Đã gửi'),
        ('accepted', 'Ứng viên đồng ý'),
        ('rejected', 'Ứng viên từ chối'),
    ], string="Trạng thái Offer", default='draft', tracking=True)

    # --- Compute state label ---
    @api.depends("state")
    def _compute_state_label(self):
        mapping = dict(self._fields["state"].selection)
        for rec in self:
            rec.state_label = mapping.get(rec.state, "")

    # --- Send Offer ---
    def action_mark_sent(self):
        for rec in self:
            if rec.state == 'draft':
                rec.confirm_token = str(uuid.uuid4())
                rec.state = 'sent'
                rec.message_post(body=_("Đã đánh dấu Offer là đã gửi."))

    # --- Candidate accepts ---
    def action_accept(self):
        for rec in self:
            rec.state = 'accepted'
            rec.applicant_id.state = 'hire_confirmed'
            rec.message_post(body=_("Ứng viên đã đồng ý Offer."))

    # --- Candidate rejects ---
    def action_reject(self):
        for rec in self:
            rec.state = 'rejected'
            rec.applicant_id.state = 'rejected'
            rec.message_post(body=_("Ứng viên đã từ chối Offer."))

    # --- Confirm from web ---
    def applicant_confirm(self, token, decision):
        self.ensure_one()
        if self.confirm_token != token:
            return False
        if decision == 'accept':
            self.action_accept()
        elif decision == 'reject':
            self.action_reject()
        return True

    # --- Base URL ---
    def get_base_url(self):
        return self.env['ir.config_parameter'].sudo().get_param('web.base.url')

    # --- Get full link ---
    def get_offer_link(self, decision):
        self.ensure_one()
        base_url = self.get_base_url()
        return f"{base_url}/offer/confirm/{self.id}?token={self.confirm_token}&decision={decision}"
