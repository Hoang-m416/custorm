from odoo import api, fields, models, _
from odoo.exceptions import ValidationError

class ForherOffboardingAssetLine(models.Model):
    _name = "forher.offboarding.asset.line"
    _description = "Dòng tài sản thu hồi"
    _order = "id asc"

    offboarding_id = fields.Many2one("forher.offboarding.assets", "Phiếu thu hồi",
                                     required=True, ondelete="cascade")
    equipment_id = fields.Many2one("maintenance.equipment", "Thiết bị/Tài sản")
    name = fields.Char("Tên tài sản")
    serial_no = fields.Char("Số S/N")

    expected_condition = fields.Selection([("good", "Nguyên vẹn")],
                                          default="good", string="Tình trạng kỳ vọng")
    return_status = fields.Selection([
        ("pending",  "Chưa trả"),
        ("returned", "Đã trả - nguyên vẹn"),
        ("damaged",  "Đã trả - hư hỏng"),
        ("missing",  "Thiếu/Không trả"),
    ], default="pending", string="Kết quả trả")

    check_notes = fields.Text("Ghi chú kiểm tra / Biên bản")
    compensation_amount = fields.Monetary("Tiền bồi thường", currency_field="currency_id", default=0.0)
    currency_id = fields.Many2one(related="offboarding_id.currency_id", store=True, readonly=True)
    check_date = fields.Datetime("Ngày kiểm tra", default=fields.Datetime.now)
    manager_user_id = fields.Many2one("res.users", "Người kiểm tra", default=lambda s: s.env.user)
    # Thêm trường upload ảnh minh chứng
    evidence_ids = fields.Many2many(
        "ir.attachment",
        "asset_line_evidence_rel", "line_id", "attachment_id",
        string="Ảnh minh chứng"
    )
    @api.constrains("return_status", "compensation_amount")
    def _check_compensation(self):
        for line in self:
            if line.return_status in ("damaged", "missing") and line.compensation_amount <= 0:
                raise ValidationError(_("Vui lòng nhập số tiền bồi thường cho dòng tài sản thiếu/hư hỏng."))
            if line.return_status in ("returned", "pending") and line.compensation_amount:
                raise ValidationError(_("Không nhập tiền bồi thường cho tài sản đã trả nguyên vẹn hoặc chưa trả."))
