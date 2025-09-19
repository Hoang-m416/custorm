# controllers/kiosk.py
from odoo import http, _, fields
from odoo.http import request
import pytz
from datetime import datetime, time, timedelta

def _today_range_utc(env):
    """Trả về cặp (day_start_utc, day_end_utc) theo timezone user để so khớp 'trong ngày'."""
    user_tz = pytz.timezone(env.user.tz or 'UTC')
    now_utc = fields.Datetime.now()               # naive UTC theo Odoo
    # Đưa now_utc -> aware UTC rồi -> local user tz
    aware_utc = now_utc.replace(tzinfo=pytz.UTC)
    local_now = aware_utc.astimezone(user_tz)
    local_date = local_now.date()
    local_start = datetime.combine(local_date, time.min).replace(tzinfo=user_tz)
    local_end   = datetime.combine(local_date, time.max).replace(tzinfo=user_tz)
    # Đưa về UTC cho domain search
    day_start_utc = local_start.astimezone(pytz.UTC)
    day_end_utc   = local_end.astimezone(pytz.UTC)
    return day_start_utc, day_end_utc

class ForherKioskController(http.Controller):
    @http.route('/forher_attendance/kiosk', type='http', auth='public', website=True, csrf=False)
    def kiosk_page(self, **kw):
        # Lấy config
        params = request.env['ir.config_parameter'].sudo()
        kiosk_company_id = int(params.get_param('forher_attendance.kiosk_company_id', '1') or '1')
        kiosk_company_name = params.get_param('forher_attendance.kiosk_company_name', 'Chi nhánh chính')

        # Nạp danh sách NV Active CHỈ THUỘC CHI NHÁNH NÀY cho dropdown
        employees = request.env['hr.employee'].sudo().search([
            ('active', '=', True),
            ('company_id', '=', kiosk_company_id)
        ], order='name')
        
        return request.render('forher_attendance.kiosk_form', {
            'employees': employees,
            'kiosk_company_name': kiosk_company_name,
        })

    @http.route('/forher_attendance/kiosk/punch', type='http', auth='public', methods=['POST'], csrf=False)
    def kiosk_punch(self, **post):
        params = request.env['ir.config_parameter'].sudo()
        fixed_loc    = params.get_param('forher_attendance.kiosk_location', 'Store Front')
        kiosk_company_id = int(params.get_param('forher_attendance.kiosk_company_id', '1') or '1')
        kiosk_company_name = params.get_param('forher_attendance.kiosk_company_name', 'Chi nhánh chính')

        pin  = (post.get('pin') or '').strip()
        code = (post.get('code') or '').strip()
        try:
            emp_id = int(post.get('employee_id') or 0)
        except Exception:
            emp_id = 0

        Employee = request.env['hr.employee'].sudo()
        Attendance = request.env['hr.attendance'].sudo()

        # 1) Xác định employee + kiểm PIN (chỉ tìm trong CHI NHÁNH NÀY)
        employee = False
        if emp_id:
            emp = Employee.browse(emp_id)
            if not emp.exists() or emp.company_id.id != kiosk_company_id:
                # Không tồn tại hoặc không thuộc chi nhánh này
                employee = False
            elif not emp.pin:
                return request.render('forher_attendance.kiosk_form', {
                    'error': _('Nhân viên này chưa được gán PIN.'),
                    'employees': Employee.search([('active', '=', True), ('company_id', '=', kiosk_company_id)], order='name'),
                    'kiosk_company_name': kiosk_company_name,
                })
            elif not pin or pin != emp.pin:
                return request.render('forher_attendance.kiosk_form', {
                    'error': _('PIN không đúng.'),
                    'employees': Employee.search([('active', '=', True), ('company_id', '=', kiosk_company_id)], order='name'),
                    'kiosk_company_name': kiosk_company_name,
                })
            else:
                employee = emp
        else:
            if pin:
                # Tìm theo PIN trong chi nhánh này
                employee = Employee.search([
                    ('pin', '=', pin), 
                    ('active', '=', True),
                    ('company_id', '=', kiosk_company_id)
                ], limit=1)
            if not employee and code:
                # Tìm theo mã nhân viên trong chi nhánh này
                employee = Employee.search([
                    '|', ('employee_code', '=', code), ('barcode', '=', code),
                    ('active', '=', True),
                    ('company_id', '=', kiosk_company_id)
                ], limit=1)

        if not employee:
            return request.render('forher_attendance.kiosk_form', {
                'error': _('Không tìm thấy nhân viên trong chi nhánh %s. Kiểm tra lựa chọn/PIN/Mã!') % kiosk_company_name,
                'employees': Employee.search([('active', '=', True), ('company_id', '=', kiosk_company_id)], order='name'),
                'kiosk_company_name': kiosk_company_name,
            })
            

        # 2) Tính “hôm nay” theo TZ user -> biên UTC
        day_start_utc, day_end_utc = _today_range_utc(request.env)

        # 3) Tra cứu bản ghi HÔM NAY (nếu có)
        today_att = Attendance.search([
            ('employee_id', '=', employee.id),
            ('check_in', '>=', fields.Datetime.to_string(day_start_utc)),
            ('check_in', '<=', fields.Datetime.to_string(day_end_utc)),
        ], limit=1, order='check_in desc')

        # 4) Logic chấm công theo yêu cầu: 1 ngày 1 lần
        if today_att:
            if today_att.check_out:
                # ĐÃ checkin + checkout = hoàn thành 1 lần chấm công trong ngày
                # -> CHẶN không cho chấm thêm (tránh gian lận)
                return request.render('forher_attendance.kiosk_form', {
                    'error': _('Bạn được chấm công 1 ngày/1 lần. Hôm nay bạn đã hoàn thành chấm công.'),
                    'employees': Employee.search([('active', '=', True), ('company_id', '=', kiosk_company_id)], order='name'),
                    'kiosk_company_name': kiosk_company_name,
                })
            else:
                # Đã checkin nhưng chưa checkout -> lần 2 = CHECKOUT
                try:
                    today_att.write({
                        'check_out': fields.Datetime.now(),
                        'check_out_note': 'Kiosk',
                        'check_out_location': fixed_loc,
                    })
                except Exception as e:
                    request.env.cr.rollback()
                    return request.render('forher_attendance.kiosk_form', {
                        'error': str(e),
                        'employees': Employee.search([('active', '=', True), ('company_id', '=', kiosk_company_id)], order='name'),
                        'kiosk_company_name': kiosk_company_name,
                    })
                
                return request.render('forher_attendance.kiosk_success', {
                    'employee': employee,
                    'action': 'checkout',
                    'location': fixed_loc,
                    'now': fields.Datetime.context_timestamp(request.env.user, fields.Datetime.now()),
                })

        # 5) Không có bản ghi hôm nay -> kiểm tra bản ghi mở từ ngày khác
        open_att = Attendance.search([
            ('employee_id', '=', employee.id),
            ('check_out', '=', False),
        ], limit=1, order='check_in desc')

        if open_att:
            # Có bản ghi mở từ ngày trước -> cần xử lý trước khi cho phép checkin mới
            return request.render('forher_attendance.kiosk_form', {
                'error': _('Bạn còn bản ghi chấm công ngày trước chưa kết thúc. Vui lòng liên hệ quản lý để xử lý.'),
                'employees': Employee.search([('active', '=', True), ('company_id', '=', kiosk_company_id)], order='name'),
                'kiosk_company_name': kiosk_company_name,
            })

        # 6) Điều kiện lý tưởng -> CHECKIN lần đầu trong ngày
        try:
            Attendance.create({
                'employee_id': employee.id,
                'check_in': fields.Datetime.now(),
                'check_in_note': 'Kiosk',
                'check_in_location': fixed_loc,
            })
        except Exception as e:
            request.env.cr.rollback()
            return request.render('forher_attendance.kiosk_form', {
                'error': str(e),
                'employees': Employee.search([('active', '=', True), ('company_id', '=', kiosk_company_id)], order='name'),
                'kiosk_company_name': kiosk_company_name,
            })

        return request.render('forher_attendance.kiosk_success', {
            'employee': employee,
            'action': 'checkin',
            'location': fixed_loc,
            'now': fields.Datetime.context_timestamp(request.env.user, fields.Datetime.now()),
        })

