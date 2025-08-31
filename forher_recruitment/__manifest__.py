{
    'name': 'Forher Recruitment A',
    'version': '1.0',
    'summary': 'Quản lý tuyển dụng cho công ty Forher',
    'category': 'Human Resources',
    'author': 'Forher IT',
    'depends': ['base', 'mail', 'website','forher_company_overview','hr'],
    'data': [
    # Security
    'security/ir.model.access.csv',

    # Backend views / actions / menus
    'views/recruitment_request_views.xml',    
    'views/applicant_views.xml',

    'views/menu_actions.xml', 
    'views/interview_views.xml',
    'views/offer_letter_views.xml',
   
    'views/website_menus.xml',
    # Email templates
    'data/email_templates.xml',
],
    'installable': True,
    'application': True,
}
