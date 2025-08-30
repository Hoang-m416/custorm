# -*- coding: utf-8 -*-
from odoo import http
from odoo.http import request
import base64

class RecruitmentApplyController(http.Controller):

    COMMON_STYLE = """
    <style>
        body { font-family: 'Helvetica Neue', Arial, sans-serif; background:#f0f2f5; margin:0; padding:20px;}
        h2 { color:#0d6efd; text-align:center; margin-bottom:20px;}
        .container { max-width: 900px; margin: 0 auto; }
        .job-item { background:#fff; padding:20px; margin:15px 0; border-radius:10px; box-shadow:0 4px 15px rgba(0,0,0,0.1); }
        .job-item a { font-size:20px; font-weight:bold; color:#0d6efd; text-decoration:none; }
        .job-item a:hover { text-decoration:underline; }
        .job-description { margin-top:10px; line-height:1.6; color:#333; }
        form { background:#fff; padding:25px; border-radius:10px; max-width:600px; margin:20px auto; box-shadow:0 6px 20px rgba(0,0,0,0.1); }
        form h3 { margin-bottom:15px; color:#0d6efd; }
        label { display:block; margin-top:10px; font-weight:bold; color:#555; }
        input, textarea, button { width:100%; padding:12px; margin-top:5px; border-radius:6px; border:1px solid #ccc; box-sizing:border-box; }
        textarea { resize: vertical; }
        button { background:#0d6efd; color:#fff; font-weight:bold; border:none; cursor:pointer; margin-top:15px; }
        button:hover { background:#0b5ed7; }
        .success-msg { background:#d1e7dd; color:#0f5132; padding:25px; border-radius:10px; text-align:center; margin:30px auto; max-width:600px; font-size:18px;}
        a.back-link { display:inline-block; margin-top:15px; color:#0d6efd; text-decoration:none; font-weight:bold; }
        a.back-link:hover { text-decoration:underline; }
    </style>
    """

    @http.route(['/apply'], type='http', auth='public', website=True)
    def apply_index(self, **kwargs):
        jobs = request.env['recruitment.request'].sudo().search([('state', '=', 'approved')])
        html = f"<html><head><title>Tuyển dụng</title>{self.COMMON_STYLE}</head><body>"
        html += "<div class='container'><h2>Danh sách yêu cầu tuyển dụng</h2>"
        for job in jobs:
            html += f"""
            <div class='job-item'>
                <a href='/apply/{job.id}'>{job.name} - {job.position or ''}</a>
                <div class='job-description'>
                    <strong>Mô tả công việc:</strong> {job.job_description or 'Chưa có mô tả.'}<br/>
                    <strong>Yêu cầu:</strong> {job.required_skills or 'Chưa có yêu cầu.'}
                </div>
            </div>
            """
        html += "</div></body></html>"
        return html

    @http.route(['/apply/<int:request_id>'], type='http', auth='public', website=True)
    def apply_form(self, request_id, **kwargs):
        job = request.env['recruitment.request'].sudo().browse(request_id)
        if not job or job.state != 'approved':
            return "<h3>Yêu cầu tuyển dụng không tồn tại hoặc chưa được duyệt.</h3>"

        html = f"""
        <html>
            <head>
                <title>Ứng tuyển {job.name}</title>
                {self.COMMON_STYLE}
            </head>
            <body>
                <div class="container">
                    <div class="job-item">
                        <h2>{job.name} - {job.position or ''}</h2>
                        <div class='job-description'>
                            <strong>Mô tả công việc:</strong> {job.job_description or 'Chưa có mô tả.'}<br/>
                            <strong>Yêu cầu:</strong> {job.required_skills or 'Chưa có yêu cầu.'}
                        </div>
                    </div>
                    <form action="/apply/submit" method="post" enctype="multipart/form-data">
                        <h3>Điền thông tin ứng viên</h3>
                        <input type="hidden" name="request_id" value="{job.id}"/>
                        <label>Họ và tên</label><input type="text" name="name" required/>
                        <label>Email</label><input type="email" name="email" required/>
                        <label>SĐT</label><input type="text" name="phone"/>
                        <label>CV / Resume (có thể bỏ trống)</label><input type="file" name="resume"/>
                        <button type="submit">Gửi hồ sơ</button>
                    </form>
                    <a href="/apply" class="back-link">← Quay về danh sách tuyển dụng</a>
                </div>
            </body>
        </html>
        """
        return html

    # Tắt CSRF cho form public
    @http.route(['/apply/submit'], type='http', auth='public', methods=['POST'], website=True, csrf=False)
    def apply_submit(self, **kwargs):
        request_id = kwargs.get('request_id')
        name = kwargs.get('name')
        email = kwargs.get('email')
        phone = kwargs.get('phone')
        resume = kwargs.get('resume')

        if not request_id or not name or not email:
            return "<h3>Vui lòng điền đầy đủ thông tin</h3>"

        job = request.env['recruitment.request'].sudo().browse(int(request_id))
        if not job or job.state != 'approved':
            return "<h3>Yêu cầu tuyển dụng không hợp lệ hoặc chưa được duyệt</h3>"

        vals = {
            'name': name,
            'email': email,
            'phone': phone,
            'request_id': job.id,
            'position_applied': job.position or '',
        }

        # Lưu CV nếu có
        if resume:
            vals['resume_filename'] = resume.filename
            vals['resume'] = base64.b64encode(resume.read())

        request.env['forher.applicant'].sudo().create(vals)

        html = f"""
        <html>
            <head>{self.COMMON_STYLE}</head>
            <body>
                <div class="container">
                    <div class="success-msg">
                        Ứng viên <strong>{name}</strong> đã nộp hồ sơ thành công cho vị trí <strong>{job.name}</strong>!
                        <br/><a href="/apply" class="back-link">← Quay về danh sách tuyển dụng</a>
                    </div>
                </div>
            </body>
        </html>
        """
        return html
