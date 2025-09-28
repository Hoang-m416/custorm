from odoo import api, fields, models, _
from odoo.exceptions import UserError


class ForherOffboardingAssets(models.Model):
    _name = "forher.offboarding.assets"
    _description = "Phiếu thu hồi tài sản khi nghỉ việc"
    _inherit = ["mail.thread", "mail.activity.mixin"]
    _order = "create_date desc"

    name = fields.Char("Mã thu hồi", default="/", readonly=True, copy=False)
    employee_id = fields.Many2one("hr.employee", "Nhân viên", required=True, tracking=True)
    employee_user_id = fields.Many2one(related="employee_id.user_id", string="User", store=True, readonly=True)
    contract_id = fields.Many2one(
        "forher.hr.contract",
        string="Hợp đồng",
        domain="[('employee_id','=',employee_id)]",
        tracking=True,
    )
    company_id = fields.Many2one("res.company", "Chi nhánh", default=lambda s: s.env.company, required=True)
    manager_id = fields.Many2one("hr.employee", "Quản lý chi nhánh (tiếp nhận)")

    reason = fields.Text("Lý do nghỉ việc")
    resignation_date = fields.Date("Ngày nghỉ việc dự kiến")
    deadline_date = fields.Date("Hạn hoàn trả", tracking=True)

    line_ids = fields.One2many("forher.offboarding.asset.line", "offboarding_id", "Danh mục tài sản")

    issue_exists = fields.Boolean("Có thiếu/hư hỏng", compute="_compute_issue_exists", store=True)
    total_compensation = fields.Monetary(
        "Tổng bồi thường",
        compute="_compute_total_compensation",
        currency_field="currency_id",
        store=True,
    )
    currency_id = fields.Many2one("res.currency", default=lambda s: s.env.company.currency_id.id)

    employee_signed = fields.Boolean("NV đã ký", tracking=True)
    manager_signed = fields.Boolean("QL Chi nhánh đã ký", tracking=True)
    accounting_done = fields.Boolean("Kế toán đã quyết toán", tracking=True)

    state = fields.Selection([
        ("draft", "Nháp"),
        ("awaiting_return", "Đã thông báo – chờ hoàn trả"),
        ("in_review", "Đang kiểm tra"),
        ("to_compensate", "Chuyển Kế toán xử lý bồi thường"),
        ("to_sign", "Lập & ký biên bản"),
        ("to_approve", "Chờ Ban Giám đốc phê duyệt"),
        ("done", "Hoàn tất"),
        ("cancel", "Hủy"),
    ], default="draft", string="Trạng thái", tracking=True)

    # helper: tất cả đều trả nguyên vẹn
    all_returned = fields.Boolean("Tất cả đã trả nguyên vẹn", compute="_compute_all_returned", store=False)

    @api.depends("line_ids.return_status")
    def _compute_all_returned(self):
        for rec in self:
            rec.all_returned = bool(rec.line_ids) and all(l.return_status == "returned" for l in rec.line_ids)

    @api.depends("line_ids.return_status")
    def _compute_issue_exists(self):
        for rec in self:
            rec.issue_exists = any(l.return_status in ("missing", "damaged") for l in rec.line_ids)

    @api.depends("line_ids.compensation_amount")
    def _compute_total_compensation(self):
        for rec in self:
            rec.total_compensation = sum(rec.line_ids.mapped("compensation_amount"))

    @api.model
    def create(self, vals):
        if vals.get("name", "/") == "/":
            vals["name"] = self.env["ir.sequence"].next_by_code("forher.offboarding.assets") or "/"
        return super().create(vals)

    # 1) Tự động liệt kê tài sản đã bàn giao (chỉ lấy tài sản chưa có trong phiếu done)
    def action_generate_lines(self):
        self.ensure_one()
        if not self.employee_id:
            raise UserError(_("Vui lòng chọn Nhân viên."))

        if self.line_ids:
            raise UserError(_("Danh mục tài sản đã tồn tại. Bạn có thể chỉnh sửa trực tiếp."))

        # Lấy toàn bộ thiết bị hiện đang gắn cho nhân viên này
        equips = self.env["maintenance.equipment"].search([
            ("employee_id", "=", self.employee_id.id)
        ])

        lines = []
        for eq in equips:
            lines.append({
                "equipment_id": eq.id,
                "name": eq.name,
                "serial_no": getattr(eq, "serial_no", "") or "",
                "expected_condition": "good",
                "return_status": "pending",
            })
        self.write({"line_ids": [(0, 0, v) for v in lines]})
        return True


    # 2) Gửi thông báo
    def action_send_notification(self):
        self.ensure_one()
        if not self.deadline_date:
            raise UserError(_("Vui lòng nhập Hạn hoàn trả."))

        t1 = self.env.ref("offboarding_assets.mail_template_notify_employee", raise_if_not_found=False)
        if t1:
            t1.send_mail(self.id, force_send=True)
        t2 = self.env.ref("offboarding_assets.mail_template_notify_manager", raise_if_not_found=False)
        if t2:
            t2.send_mail(self.id, force_send=True)

        self.message_post(body=_("Đã gửi thông báo thu hồi tài sản."))
        self.state = "awaiting_return"

    # 3) Bắt đầu kiểm tra
    def action_start_review(self):
        self.ensure_one()
        if not self.line_ids:
            raise UserError(_("Chưa có danh mục tài sản để kiểm tra."))

        if self.all_returned:
            self.state = "to_sign"
            self.message_post(body=_("Tất cả tài sản đã trả nguyên vẹn → Chuyển sang bước Lập & ký biên bản."))
        elif self.issue_exists:
            self.state = "to_compensate"
            self.message_post(body=_("Có tài sản thiếu hoặc hư hỏng → Chuyển sang Kế toán xử lý bồi thường."))
        else:
            self.state = "in_review"
            self.message_post(body=_("Đang kiểm tra tình trạng tài sản."))

    # 4) Chuyển Kế toán
    def action_send_to_accounting(self):
        self.ensure_one()
        if not self.issue_exists:
            raise UserError(_("Không có tài sản thiếu/hư hỏng."))
        t = self.env.ref("offboarding_assets.mail_template_to_accounting", raise_if_not_found=False)
        if t:
            t.send_mail(self.id, force_send=True)
        self.message_post(body=_("Đã chuyển Kế toán xử lý bồi thường."))
        self.state = "to_compensate"

    def action_mark_accounting_done(self):
        self.ensure_one()
        self.accounting_done = True
        self.message_post(body=_("Kế toán đã quyết toán bồi thường."))
        self.state = "to_sign"

    # 5) Lập biên bản & ký
    def action_generate_report(self):
        self.ensure_one()
        return self.env.ref("offboarding_assets.action_report_offboarding_assets").report_action(self)

    def action_mark_signed(self):
        """Context: {'by': 'employee'|'manager'}"""
        self.ensure_one()
        by = (self.env.context or {}).get("by", "employee")
        if by == "employee":
            self.employee_signed = True
            self.message_post(body=_("Nhân viên đã ký xác nhận."))
        else:
            self.manager_signed = True
            self.message_post(body=_("Quản lý chi nhánh đã ký xác nhận."))
        if self.employee_signed and self.manager_signed:
            self.state = "to_approve"

    # 6) Phê duyệt
    def action_approve(self):
        self.ensure_one()
        if not (self.employee_signed and self.manager_signed):
            raise UserError(_("Cần đủ chữ ký của Nhân viên và Quản lý chi nhánh."))
        if self.issue_exists and not self.accounting_done:
            raise UserError(_("Cần Kế toán quyết toán bồi thường trước khi phê duyệt."))

        # 1. Thu hồi thiết bị: xóa liên kết employee_id
        if self.employee_id:
            equips = self.env["maintenance.equipment"].search([("employee_id", "=", self.employee_id.id)])
            if equips:
                equips.sudo().write({"employee_id": False})
            self.message_post(body=_("Đã thu hồi tất cả thiết bị khỏi nhân viên."))

        # 2. Hoàn tất phiếu
        self.state = "done"
        self.message_post(body=_("Đã phê duyệt và hoàn tất thu hồi tài sản."))

        # 3. Cập nhật trạng thái hợp đồng
        if self.contract_id and "state" in self.contract_id._fields:
            try:
                self.contract_id.sudo().write({"state": "close"})
                self.contract_id.message_post(
                    body=_("Thu hồi tài sản hoàn tất: cập nhật trạng thái hợp đồng → Đã thanh lý (close).")
                )
            except Exception:
                pass


    # 7) Hủy hồ sơ
    def action_cancel(self):
        for rec in self:
            if rec.state == "done":
                raise UserError(_("Hồ sơ đã hoàn tất, không thể hủy."))
            rec.write({"state": "cancel"})
            rec.message_post(body=_("Đã hủy quy trình thu hồi tài sản."))
        return True

    # 8) Đưa về Nháp
    def action_reset_to_draft(self):
        for rec in self:
            if rec.state not in ("cancel",):
                raise UserError(_("Chỉ có thể đưa về Nháp khi đang ở trạng thái Hủy."))
            rec.write({
                "state": "draft",
                "employee_signed": False,
                "manager_signed": False,
                "accounting_done": False,
            })
            rec.message_post(body=_("Đã đưa hồ sơ về trạng thái Nháp."))
        return True


class HrEmployee(models.Model):
    _inherit = "hr.employee"

    def action_create_offboarding_from_employee(self):
        self.ensure_one()
        contract = self.env["forher.hr.contract"].search(
            [("employee_id", "=", self.id)], order="id desc", limit=1
        )
        offb = self.env["forher.offboarding.assets"].create({
            "employee_id": self.id,
            "company_id": self.company_id.id or self.env.company.id,
            "manager_id": self.parent_id.id if self.parent_id else False,
            "contract_id": contract.id or False,
        })
        return {
            "type": "ir.actions.act_window",
            "res_model": "forher.offboarding.assets",
            "view_mode": "form",
            "res_id": offb.id,
        }


class ForherOffboardingAssetLine(models.Model):
    _name = "forher.offboarding.asset.line"
    _description = "Chi tiết tài sản trong phiếu thu hồi"
    _inherit = ["mail.thread", "mail.activity.mixin"]

    offboarding_id = fields.Many2one(
        "forher.offboarding.assets",
        string="Phiếu thu hồi",
        ondelete="cascade"
    )
    equipment_id = fields.Many2one("maintenance.equipment", "Tài sản")
    name = fields.Char("Tên tài sản")
    serial_no = fields.Char("Số serial")
    expected_condition = fields.Selection([
        ("good", "Bình thường"),
        ("damaged", "Hư hỏng"),
    ], string="Tình trạng dự kiến", default="good")
    return_status = fields.Selection([
        ("pending", "Chưa hoàn trả"),
        ("returned", "Đã trả - nguyên vẹn"),
        ("missing", "Thiếu"),
        ("damaged", "Đã trả - hư hỏng"),
    ], string="Kết quả hoàn trả", default="pending", tracking=True)
    compensation_amount = fields.Monetary("Số tiền bồi thường", currency_field="currency_id")
    check_notes = fields.Text("Ghi chú kiểm tra / Biên bản")
    # Thêm trường ảnh minh chứng
    evidence_ids = fields.Many2many(
        "ir.attachment", 
        "asset_line_evidence_rel", "line_id", "attachment_id",
        string="Ảnh minh chứng"
    )
    currency_id = fields.Many2one("res.currency", default=lambda s: s.env.company.currency_id.id)

    employee_signed = fields.Boolean("NV đã ký")
    manager_signed = fields.Boolean("QL đã ký")
    director_signed = fields.Boolean("BGĐ đã ký")

    @api.onchange("return_status")
    def _onchange_return_status(self):
        if self.offboarding_id:
            if all(line.return_status == "returned" for line in self.offboarding_id.line_ids):
                self.offboarding_id.state = "to_sign"
            elif any(line.return_status in ("missing", "damaged") for line in self.offboarding_id.line_ids):
                self.offboarding_id.state = "to_compensate"
            else:
                self.offboarding_id.state = "in_review"
    