# controllers/kiosk.py
from odoo import http, _, fields
from odoo.http import request
import pytz
from datetime import datetime, time

def _today_range_utc(env):
    """Trả về cặp (day_start_utc, day_end_utc) theo timezone user để so khớp 'trong ngày'."""
    user_tz = pytz.timezone(env.user.tz or 'UTC')
    now_utc = fields.Datetime.now()
    aware_utc = now_utc.replace(tzinfo=pytz.UTC)
    local_now = aware_utc.astimezone(user_tz)
    local_date = local_now.date()
    local_start = datetime.combine(local_date, time.min).replace(tzinfo=user_tz)
    local_end   = datetime.combine(local_date, time.max).replace(tzinfo=user_tz)
    day_start_utc = local_start.astimezone(pytz.UTC)
    day_end_utc   = local_end.astimezone(pytz.UTC)
    return day_start_utc, day_end_utc

class ForherKioskController(http.Controller):

    def _get_kiosk_employees(self):
        """Lấy danh sách nhân viên hiển thị trên kiosk theo Record Rule."""
        user = request.env.user
        Employee = request.env['hr.employee']  # KHÔNG sudo()

        # Search tất cả active employee → Record Rule sẽ tự filter
        employees = Employee.search([('active', '=', True)], order='name')

        # Lấy company_ids của employee đang đăng nhập (dùng để hiển thị tên chi nhánh)
        employee = user.employee_ids[:1]
        company_ids = employee.company_id.child_ids.ids + [employee.company_id.id] if employee else []

        return employees, company_ids


    @http.route('/forher_attendance/kiosk', type='http', auth='user', website=True, csrf=False)
    def kiosk_page(self, **kw):
        employees, company_ids = self._get_kiosk_employees()
        return request.render('forher_attendance.kiosk_form', {
            'employees': employees,
            'kiosk_company_name': ', '.join(request.env['res.company'].browse(company_ids).mapped('name')),
        })

    @http.route('/forher_attendance/kiosk/punch', type='http', auth='user', methods=['POST'], csrf=False)
    def kiosk_punch(self, **post):
        fixed_loc = request.env['ir.config_parameter'].sudo().get_param('forher_attendance.kiosk_location', 'Store Front')
        pin  = (post.get('pin') or '').strip()
        code = (post.get('code') or '').strip()
        try:
            emp_id = int(post.get('employee_id') or 0)
        except Exception:
            emp_id = 0

        Employee = request.env['hr.employee'].sudo()
        Attendance = request.env['hr.attendance'].sudo()
        employees, company_ids = self._get_kiosk_employees()

        # Xác định employee
        employee = False
        if emp_id:
            emp = Employee.browse(emp_id)
            if not emp.exists() or emp.company_id.id not in company_ids:
                employee = False
            elif not emp.pin:
                return self._render_error('Nhân viên này chưa được gán PIN.', employees)
            elif not pin or pin != emp.pin:
                return self._render_error('PIN không đúng.', employees)
            else:
                employee = emp
        else:
            if pin:
                employee = Employee.search([('pin', '=', pin), ('active', '=', True)], limit=1)
            if not employee and code:
                employee = Employee.search([
                    '|', ('employee_code', '=', code), ('barcode', '=', code),
                    ('active', '=', True)
                ], limit=1)

        if not employee:
            return self._render_error(_('Không tìm thấy nhân viên. Kiểm tra lựa chọn/PIN/Mã!'), employees)

        # Tính "hôm nay" theo TZ user
        day_start_utc, day_end_utc = _today_range_utc(request.env)

        # Tra cứu bản ghi hôm nay
        today_att = Attendance.search([
            ('employee_id', '=', employee.id),
            ('check_in', '>=', fields.Datetime.to_string(day_start_utc)),
            ('check_in', '<=', fields.Datetime.to_string(day_end_utc)),
        ], limit=1, order='check_in desc')

        # Nếu đã check-in & check-out -> thông báo 1 ngày 1 lần
        if today_att and today_att.check_out:
            return self._render_error('Bạn được chấm công 1 ngày/1 lần. Hôm nay bạn đã hoàn thành chấm công.', employees)

        # Nếu đã check-in hôm nay nhưng chưa check-out -> thực hiện check-out
        if today_att and not today_att.check_out:
            try:
                today_att.write({
                    'check_out': fields.Datetime.now(),
                    'check_out_note': 'Kiosk',
                    'check_out_location': fixed_loc,
                })
            except Exception as e:
                request.env.cr.rollback()
                return self._render_error(str(e), employees)

            return request.render('forher_attendance.kiosk_success', {
                'employee': employee,
                'action': 'checkout',
                'location': fixed_loc,
                'now': fields.Datetime.context_timestamp(request.env.user, fields.Datetime.now()),
            })

        # Kiểm tra bản ghi mở từ ngày trước
        open_att = Attendance.search([
            ('employee_id', '=', employee.id),
            ('check_out', '=', False),
        ], limit=1, order='check_in desc')

        if open_att:
            return self._render_error('Bạn còn bản ghi chấm công ngày trước chưa kết thúc. Vui lòng liên hệ quản lý để xử lý.', employees)

        # Check-in lần đầu trong ngày
        try:
            Attendance.create({
                'employee_id': employee.id,
                'check_in': fields.Datetime.now(),
                'check_in_note': 'Kiosk',
                'check_in_location': fixed_loc,
            })
        except Exception as e:
            request.env.cr.rollback()
            return self._render_error(str(e), employees)

        return request.render('forher_attendance.kiosk_success', {
            'employee': employee,
            'action': 'checkin',
            'location': fixed_loc,
            'now': fields.Datetime.context_timestamp(request.env.user, fields.Datetime.now()),
        })

    def _render_error(self, message, employees):
        """Helper render template lỗi"""
        return request.render('forher_attendance.kiosk_form', {
            'error': message,
            'employees': employees,
        })
    
    @http.route('/forher_attendance/kiosk/thank_you', type='http', auth='user', website=True, csrf=False)
    def kiosk_thank_you(self, **kw):
        """Trang cảm ơn sau khi chấm công"""
        return request.render('forher_attendance.kiosk_thank_you')

