# -*- coding: utf-8 -*-
import email

from odoo import models, fields
from datetime import datetime, timedelta, date



class Employee_Reg(models.Model):
    _inherit = 'hr.employee'


    date_start = fields.Date(string="Relieving Date")
    emp = fields.Char(string="emp")

    skill = fields.Many2one('skill.skill', string="Primary Skill")

    def print_date(r):
        a = r.date_start
        print(a,"dtaeeee")

    def print_pdf(self):
        return self.env.ref("ults_hr_employee.employee_pdf_id").report_action(self)

    def send_email(self):
        template = self.env.ref('ults_hr_employee.mail_template_id')
        user = self.env.user.email
        for rec in self :
            print("hiiiiiiiiiiiiiiiiiiiiiiiiiii",user)
            if self.env.user.email:
                template.send_mail(rec.id,force_send=True)
        print(template,'llllllllllllllllllllllllllllllllllllllllllllllll')

