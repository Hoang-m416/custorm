# -*- coding: utf-8 -*-
from odoo import models, fields, api, _
from odoo.exceptions import ValidationError
from datetime import date, timedelta

# =========================================================
# LOẠI NGHỈ (LEAVE TYPE)
# =========================================================
class LeaveType(models.Model):
    _name = "forher.leave.type"
    _description = "Loại nghỉ phép"

    name = fields.Char("Tên loại nghỉ", required=True)
    code = fields.Char("Mã loại nghỉ")
    max_days = fields.Integer("Số ngày tối đa / năm", default=12)
    is_paid = fields.Boolean("Có lương", default=True)
    description = fields.Text("Mô tả")



# =========================================================
# NGÀY LỄ (HOLIDAY CALENDAR)
# =========================================================
class HolidayCalendar(models.Model):
    _name = "forher.holiday.calendar"
    _description = "Lịch ngày lễ"
    _rec_name = "name"

    name = fields.Char("Tên ngày lễ", required=True)
    date = fields.Date("Ngày lễ", required=True)
    description = fields.Text("Mô tả")

    _sql_constraints = [
        ("unique_holiday_date", "unique(date)", "Ngày lễ này đã tồn tại rồi!"),
    ]

    @api.model
    def create(self, vals):
        rec = super().create(vals)

        # 1. Tìm hoặc tạo leave type "Public Holiday"
        leave_type = self.env["forher.leave.type"].search([("code", "=", "HOLIDAY")], limit=1)
        if not leave_type:
            leave_type = self.env["forher.leave.type"].create({
                "name": "Public Holiday",
                "code": "HOLIDAY",
                "max_days": 0,
                "is_paid": True,
                "description": "Ngày nghỉ lễ toàn công ty",
            })

        # 2. Tạo leave request mà không liên kết với nhân viên
        self.env["forher.leave.request"].create({
            "employee_id": False,  # Không gán employee
            "leave_type_id": leave_type.id,
            "start_date": rec.date,
            "end_date": rec.date,
            "state": "approve",
            "name": rec.name,
        })

        return rec



# =========================================================
# NGHỈ PHÉP (LEAVE REQUEST)
# =========================================================
class LeaveRequest(models.Model):
    _name = "forher.leave.request"
    _description = "Yêu cầu nghỉ phép"
    _inherit = ['mail.thread', 'mail.activity.mixin']

    name = fields.Char("Tiêu đề", compute="_compute_name", store=True)
    employee_id = fields.Many2one("hr.employee", string="Nhân viên", required=False, ondelete="cascade")
    leave_type_id = fields.Many2one("forher.leave.type", string="Loại nghỉ", required=True)
    start_date = fields.Date("Ngày bắt đầu", required=True)
    end_date = fields.Date("Ngày kết thúc", required=True)
    days_count = fields.Integer("Số ngày nghỉ", compute="_compute_days", store=True)
    state = fields.Selection([
        ("draft", "Nháp"),
        ("confirm", "Chờ duyệt"),
        ("approve", "Đã duyệt"),
        ("reject", "Từ chối"),
    ], default="draft", string="Trạng thái", tracking=True)

    note = fields.Text("Ghi chú")
    is_holiday_leave = fields.Boolean("Nghỉ trùng ngày lễ", compute="_compute_is_holiday", store=True)

    show_in_calendar = fields.Boolean("Hiển thị trên calendar", compute="_compute_show_in_calendar", store=True)

    @api.depends("leave_type_id")
    def _compute_show_in_calendar(self):
        for rec in self:
            rec.show_in_calendar = True if rec.leave_type_id.code == "HOLIDAY" or rec.employee_id else True

    remaining_days = fields.Integer(
        "Số ngày nghỉ còn lại",
        compute="_compute_remaining_days",
        store=False
    )

    @api.depends("employee_id", "leave_type_id")
    def _compute_remaining_days(self):
        for rec in self:
            if rec.employee_id and rec.leave_type_id:
                year = rec.start_date.year if rec.start_date else date.today().year
                leaves_taken = self.search([
                    ("employee_id", "=", rec.employee_id.id),
                    ("leave_type_id", "=", rec.leave_type_id.id),
                    ("state", "=", "approve"),
                    ("start_date", ">=", f"{year}-01-01"),
                    ("end_date", "<=", f"{year}-12-31"),
                ])
                total_taken = sum(leaves_taken.mapped("days_count"))
                rec.remaining_days = rec.leave_type_id.max_days - total_taken
            else:
                rec.remaining_days = 0

    # ===============================
    # COMPUTE
    # ===============================
    @api.depends("employee_id", "leave_type_id", "start_date", "end_date")
    def _compute_name(self):
        for rec in self:
            if rec.employee_id and rec.leave_type_id:
                rec.name = f"{rec.employee_id.name} - {rec.leave_type_id.name}"
            elif rec.leave_type_id and rec.leave_type_id.code == "HOLIDAY":
                rec.name = rec.leave_type_id.name
            else:
                rec.name = "Yêu cầu nghỉ phép"


    @api.depends("start_date", "end_date")
    def _compute_days(self):
        for rec in self:
            if rec.start_date and rec.end_date:
                delta = (rec.end_date - rec.start_date).days + 1
                rec.days_count = delta if delta > 0 else 0
            else:
                rec.days_count = 0

    @api.depends("start_date", "end_date")
    def _compute_is_holiday(self):
        holidays = self.env["forher.holiday.calendar"].search([])
        for rec in self:
            rec.is_holiday_leave = False
            if rec.start_date and rec.end_date:
                leave_days = [rec.start_date + timedelta(days=i) for i in range((rec.end_date - rec.start_date).days + 1)]
                holiday_days = holidays.mapped("date")
                if any(day in holiday_days for day in leave_days):
                    rec.is_holiday_leave = True

    # ===============================
    # VALIDATION
    # ===============================
    @api.constrains("start_date", "end_date")
    def _check_date_range(self):
        for rec in self:
            if rec.start_date and rec.end_date and rec.start_date > rec.end_date:
                raise ValidationError("Ngày bắt đầu không được lớn hơn ngày kết thúc.")

    @api.constrains("days_count", "leave_type_id", "employee_id", "state")
    def _check_max_days(self):
        for rec in self:
            if rec.state in ["approve", "confirm"] and rec.leave_type_id.max_days:
                year = rec.start_date.year if rec.start_date else date.today().year

                # Lấy tất cả các leave đã duyệt của loại này
                leaves_taken = self.search([
                    ("employee_id", "=", rec.employee_id.id),
                    ("leave_type_id", "=", rec.leave_type_id.id),
                    ("state", "=", "approve"),
                    ("start_date", ">=", f"{year}-01-01"),
                    ("end_date", "<=", f"{year}-12-31"),
                ])

                # Tạo tập hợp các ngày nghỉ đã duyệt (loại trừ HOLIDAY)
                taken_dates = set()
                for leave in leaves_taken:
                    if leave.leave_type_id.code != "HOLIDAY":
                        start = max(leave.start_date, date(year,1,1))
                        end = min(leave.end_date, date(year,12,31))
                        taken_dates.update([start + timedelta(days=i) for i in range((end - start).days + 1)])

                # Ngày mới request (loại trừ HOLIDAY)
                new_dates = set()
                if rec.leave_type_id.code != "HOLIDAY":
                    start = rec.start_date
                    end = rec.end_date
                    new_dates.update([start + timedelta(days=i) for i in range((end - start).days + 1)])

                # Tổng số ngày nghỉ thực sự
                total_days = len(taken_dates.union(new_dates))

                if total_days > rec.leave_type_id.max_days:
                    raise ValidationError(_(
                        f"Nhân viên {rec.employee_id.name} đã vượt quá số ngày nghỉ tối đa "
                        f"({rec.leave_type_id.max_days}) cho loại {rec.leave_type_id.name}."
                    ))


    # ===============================
    # ACTIONS
    # ===============================
    def action_confirm(self):
        self.write({"state": "confirm"})

    def action_approve(self):
        self.write({"state": "approve"})

    def action_reject(self):
        self.write({"state": "reject"})

    def action_reset_draft(self):
        self.write({"state": "draft"})
