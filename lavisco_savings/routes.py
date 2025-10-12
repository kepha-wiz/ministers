from flask import render_template, redirect, url_for, flash, request, jsonify, make_response, send_file
from flask_login import login_user, logout_user, current_user, login_required
from datetime import datetime, timedelta
from models import db, User, Minister, Payment
from forms import LoginForm, ChangePasswordForm, MinisterForm, PaymentForm, ReportForm
import io
import csv
from reportlab.lib.pagesizes import letter
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.lib import colors
from reportlab.lib.units import inch

def init_routes(app):
    @app.route('/')
    @app.route('/index')
    def index():
        return redirect(url_for('dashboard'))
    
    @app.route('/login', methods=['GET', 'POST'])
    def login():
        if current_user.is_authenticated:
            return redirect(url_for('dashboard'))
        form = LoginForm()
        if form.validate_on_submit():
            user = User.query.filter_by(username=form.username.data).first()
            if user is None or not user.check_password(form.password.data):
                flash('Invalid username or password', 'danger')
                return redirect(url_for('login'))
            login_user(user, remember=form.remember_me.data)
            return redirect(url_for('dashboard'))
        return render_template('login.html', title='Sign In', form=form)
    
    @app.route('/logout')
    def logout():
        logout_user()
        return redirect(url_for('login'))
    
    @app.route('/dashboard')
    @login_required
    def dashboard():
        # Get dashboard statistics
        total_ministers = Minister.query.count()
        total_savings = db.session.query(db.func.sum(Payment.amount)).scalar() or 0
        
        # Get top 3 savers
        top_savers = Minister.query.order_by(Minister.total_savings.desc()).limit(3).all()
        
        # Get recent payments
        recent_payments = Payment.query.order_by(Payment.created_at.desc()).limit(5).all()
        
        # Check if today is Sunday (weekday 6)
        today = datetime.now()
        is_sunday = today.weekday() == 6
        
        return render_template('dashboard.html', title='Dashboard', 
                               total_ministers=total_ministers,
                               total_savings=total_savings,
                               top_savers=top_savers,
                               recent_payments=recent_payments,
                               is_sunday=is_sunday)
    
    @app.route('/ministers')
    @login_required
    def ministers():
        search = request.args.get('search', '')
        if search:
            ministers = Minister.query.filter(
                db.or_(
                    Minister.full_name.contains(search),
                    Minister.department.contains(search)
                )
            ).all()
        else:
            ministers = Minister.query.all()
        return render_template('ministers.html', title='Ministers', ministers=ministers, search=search)
    
    @app.route('/ministers/add', methods=['GET', 'POST'])
    @login_required
    def add_minister():
        form = MinisterForm()
        if form.validate_on_submit():
            minister = Minister(
                full_name=form.full_name.data,
                department=form.department.data,
                phone=form.phone.data,
                email=form.email.data,
                date_joined=form.date_joined.data
            )
            db.session.add(minister)
            db.session.commit()
            flash(f'Minister {minister.full_name} has been added successfully!', 'success')
            return redirect(url_for('ministers'))
        return render_template('minister_form.html', title='Add Minister', form=form)
    
    @app.route('/ministers/edit/<int:id>', methods=['GET', 'POST'])
    @login_required
    def edit_minister(id):
        minister = Minister.query.get_or_404(id)
        form = MinisterForm(obj=minister)
        if form.validate_on_submit():
            minister.full_name = form.full_name.data
            minister.department = form.department.data
            minister.phone = form.phone.data
            minister.email = form.email.data
            minister.date_joined = form.date_joined.data
            minister.updated_at = datetime.utcnow()
            db.session.commit()
            flash(f'Minister {minister.full_name} has been updated successfully!', 'success')
            return redirect(url_for('ministers'))
        return render_template('minister_form.html', title='Edit Minister', form=form, minister=minister)
    
    @app.route('/ministers/delete/<int:id>', methods=['POST'])
    @login_required
    def delete_minister(id):
        minister = Minister.query.get_or_404(id)
        db.session.delete(minister)
        db.session.commit()
        flash(f'Minister {minister.full_name} has been deleted successfully!', 'success')
        return redirect(url_for('ministers'))
    
    @app.route('/payments')
    @login_required
    def payments():
        # Get filter parameters
        start_date = request.args.get('start_date')
        end_date = request.args.get('end_date')
        
        # Build query
        query = Payment.query
        
        # Apply date filters if provided
        if start_date:
            query = query.filter(Payment.payment_date >= datetime.strptime(start_date, '%Y-%m-%d').date())
        if end_date:
            query = query.filter(Payment.payment_date <= datetime.strptime(end_date, '%Y-%m-%d').date())
        
        # Execute query
        payments = query.order_by(Payment.payment_date.desc()).all()
        
        return render_template('payments.html', title='Payments', payments=payments, 
                               start_date=start_date, end_date=end_date)
    
    @app.route('/payments/add', methods=['GET', 'POST'])
    @login_required
    def add_payment():
        form = PaymentForm()
        if form.validate_on_submit():
            # Calculate week number if not provided
            week_number = form.week_number.data
            if not week_number:
                # ISO week number
                week_number = form.payment_date.data.isocalendar()[1]
            
            payment = Payment(
                minister_id=form.minister_id.data,
                amount=form.amount.data,
                payment_date=form.payment_date.data,
                week_number=week_number,
                note=form.note.data
            )
            db.session.add(payment)
            db.session.commit()
            
            # Update minister's total savings
            minister = Minister.query.get(form.minister_id.data)
            minister.update_total_savings()
            
            flash(f'Payment of ${payment.amount:.2f} for {minister.full_name} has been recorded successfully!', 'success')
            return redirect(url_for('payments'))
        return render_template('payment_form.html', title='Record Payment', form=form)
    
    @app.route('/payments/edit/<int:id>', methods=['GET', 'POST'])
    @login_required
    def edit_payment(id):
        payment = Payment.query.get_or_404(id)
        form = PaymentForm(obj=payment)
        if form.validate_on_submit():
            # Store old minister ID for updating totals
            old_minister_id = payment.minister_id
            
            # Update payment details
            payment.minister_id = form.minister_id.data
            payment.amount = form.amount.data
            payment.payment_date = form.payment_date.data
            payment.week_number = form.week_number.data if form.week_number.data else form.payment_date.data.isocalendar()[1]
            payment.note = form.note.data
            
            db.session.commit()
            
            # Update totals for both old and new ministers if changed
            if old_minister_id != payment.minister_id:
                old_minister = Minister.query.get(old_minister_id)
                old_minister.update_total_savings()
            
            minister = Minister.query.get(payment.minister_id)
            minister.update_total_savings()
            
            flash(f'Payment has been updated successfully!', 'success')
            return redirect(url_for('payments'))
        return render_template('payment_form.html', title='Edit Payment', form=form, payment=payment)
    
    @app.route('/payments/delete/<int:id>', methods=['POST'])
    @login_required
    def delete_payment(id):
        payment = Payment.query.get_or_404(id)
        minister_id = payment.minister_id
        db.session.delete(payment)
        db.session.commit()
        
        # Update minister's total savings
        minister = Minister.query.get(minister_id)
        minister.update_total_savings()
        
        flash(f'Payment has been deleted successfully!', 'success')
        return redirect(url_for('payments'))
    
    @app.route('/reports')
    @login_required
    def reports():
        form = ReportForm()
        return render_template('reports.html', title='Reports', form=form)
    
    @app.route('/reports/generate/<report_type>', methods=['POST'])
    @login_required
    def generate_report(report_type):
        form = ReportForm()
        if not form.validate_on_submit():
            flash('Invalid date range provided', 'danger')
            return redirect(url_for('reports'))
        
        start_date = form.start_date.data
        end_date = form.end_date.data
        
        # Format dates for filename
        start_str = start_date.strftime('%Y%m%d')
        end_str = end_date.strftime('%Y%m%d')
        
        if report_type == 'summary':
            return generate_summary_report(start_date, end_date, start_str, end_str)
        elif report_type == 'detailed':
            return generate_detailed_report(start_date, end_date, start_str, end_str)
        else:
            flash('Invalid report type', 'danger')
            return redirect(url_for('reports'))
    
    def generate_summary_report(start_date, end_date, start_str, end_str):
        # Get payments in date range
        payments = Payment.query.filter(
            Payment.payment_date >= start_date,
            Payment.payment_date <= end_date
        ).all()
        
        # Calculate summary statistics
        total_amount = sum(p.amount for p in payments)
        total_payments = len(payments)
        
        # Group by minister
        minister_totals = {}
        for payment in payments:
            minister_id = payment.minister_id
            if minister_id not in minister_totals:
                minister_totals[minister_id] = {
                    'name': payment.minister.full_name,
                    'amount': 0,
                    'count': 0
                }
            minister_totals[minister_id]['amount'] += payment.amount
            minister_totals[minister_id]['count'] += 1
        
        # Create CSV
        output = io.StringIO()
        writer = csv.writer(output)
        
        # Write header
        writer.writerow(['Lavisco Ministers Saving Scheme - Summary Report'])
        writer.writerow([f'Period: {start_date} to {end_date}'])
        writer.writerow([''])
        
        # Write summary statistics
        writer.writerow(['Summary Statistics'])
        writer.writerow(['Total Amount', f'UGX{total_amount:.2f}'])
        writer.writerow(['Total Payments', total_payments])
        writer.writerow([''])
        
        # Write minister totals
        writer.writerow(['Minister Contributions'])
        writer.writerow(['Minister Name', 'Total Amount', 'Number of Payments'])
        
        for minister_id, data in sorted(minister_totals.items(), key=lambda x: x[1]['amount'], reverse=True):
            writer.writerow([data['name'], f'${data["amount"]:.2f}', data['count']])
        
        # Prepare response
        output.seek(0)
        response = make_response(output.getvalue())
        response.headers['Content-Disposition'] = f'attachment; filename=summary_report_{start_str}_to_{end_str}.csv'
        response.headers['Content-type'] = 'text/csv'
        return response
    
    def generate_detailed_report(start_date, end_date, start_str, end_str):
        # Get payments in date range
        payments = Payment.query.filter(
            Payment.payment_date >= start_date,
            Payment.payment_date <= end_date
        ).order_by(Payment.payment_date).all()
        
        # Create CSV
        output = io.StringIO()
        writer = csv.writer(output)
        
        # Write header
        writer.writerow(['Lavisco Ministers Saving Scheme - Detailed Report'])
        writer.writerow([f'Period: {start_date} to {end_date}'])
        writer.writerow([''])
        
        # Write payment details
        writer.writerow(['Payment Details'])
        writer.writerow(['Date', 'Minister Name', 'Amount', 'Week Number', 'Note'])
        
        for payment in payments:
            writer.writerow([
                payment.payment_date.strftime('%Y-%m-%d'),
                payment.minister.full_name,
                f'${payment.amount:.2f}',
                payment.week_number or '',
                payment.note or ''
            ])
        
        # Prepare response
        output.seek(0)
        response = make_response(output.getvalue())
        response.headers['Content-Disposition'] = f'attachment; filename=detailed_report_{start_str}_to_{end_str}.csv'
        response.headers['Content-type'] = 'text/csv'
        return response
    
    @app.route('/reports/pdf/<report_type>', methods=['POST'])
    @login_required
    def generate_pdf_report(report_type):
        form = ReportForm()
        if not form.validate_on_submit():
            flash('Invalid date range provided', 'danger')
            return redirect(url_for('reports'))
        
        start_date = form.start_date.data
        end_date = form.end_date.data
        
        # Format dates for filename
        start_str = start_date.strftime('%Y%m%d')
        end_str = end_date.strftime('%Y%m%d')
        
        if report_type == 'summary':
            return generate_summary_pdf(start_date, end_date, start_str, end_str)
        elif report_type == 'detailed':
            return generate_detailed_pdf(start_date, end_date, start_str, end_str)
        else:
            flash('Invalid report type', 'danger')
            return redirect(url_for('reports'))
    
    def generate_summary_pdf(start_date, end_date, start_str, end_str):
        # Get payments in date range
        payments = Payment.query.filter(
            Payment.payment_date >= start_date,
            Payment.payment_date <= end_date
        ).all()
        
        # Calculate summary statistics
        total_amount = sum(p.amount for p in payments)
        total_payments = len(payments)
        
        # Group by minister
        minister_totals = {}
        for payment in payments:
            minister_id = payment.minister_id
            if minister_id not in minister_totals:
                minister_totals[minister_id] = {
                    'name': payment.minister.full_name,
                    'amount': 0,
                    'count': 0
                }
            minister_totals[minister_id]['amount'] += payment.amount
            minister_totals[minister_id]['count'] += 1
        
        # Create PDF
        buffer = io.BytesIO()
        doc = SimpleDocTemplate(buffer, pagesize=letter)
        elements = []
        
        # Get styles
        styles = getSampleStyleSheet()
        title_style = styles['h1']
        heading_style = styles['h2']
        normal_style = styles['Normal']
        
        # Add title
        elements.append(Paragraph("Lavisco Ministers Saving Scheme - Summary Report", title_style))
        elements.append(Spacer(1, 12))
        
        # Add date range
        elements.append(Paragraph(f"Period: {start_date} to {end_date}", normal_style))
        elements.append(Spacer(1, 12))
        
        # Add summary statistics
        elements.append(Paragraph("Summary Statistics", heading_style))
        elements.append(Spacer(1, 6))
        
        summary_data = [
            ['Total Amount', f'${total_amount:.2f}'],
            ['Total Payments', str(total_payments)]
        ]
        
        summary_table = Table(summary_data, colWidths=[2*inch, 2*inch])
        summary_table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), colors.grey),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
            ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (-1, 0), 12),
            ('BOTTOMPADDING', (0, 0), (-1, 0), 12),
            ('BACKGROUND', (0, 1), (-1, -1), colors.beige),
            ('GRID', (0, 0), (-1, -1), 1, colors.black)
        ]))
        
        elements.append(summary_table)
        elements.append(Spacer(1, 12))
        
        # Add minister totals
        elements.append(Paragraph("Minister Contributions", heading_style))
        elements.append(Spacer(1, 6))
        
        minister_data = [['Minister Name', 'Total Amount', 'Number of Payments']]
        
        for minister_id, data in sorted(minister_totals.items(), key=lambda x: x[1]['amount'], reverse=True):
            minister_data.append([
                data['name'],
                f'${data["amount"]:.2f}',
                str(data['count'])
            ])
        
        minister_table = Table(minister_data, colWidths=[2.5*inch, 1.5*inch, 1.5*inch])
        minister_table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), colors.grey),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
            ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (-1, 0), 12),
            ('BOTTOMPADDING', (0, 0), (-1, 0), 12),
            ('BACKGROUND', (0, 1), (-1, -1), colors.beige),
            ('GRID', (0, 0), (-1, -1), 1, colors.black)
        ]))
        
        elements.append(minister_table)
        
        # Build PDF
        doc.build(elements)
        
        buffer.seek(0)
        response = make_response(buffer.getvalue())
        response.headers['Content-Disposition'] = f'attachment; filename=summary_report_{start_str}_to_{end_str}.pdf'
        response.headers['Content-type'] = 'application/pdf'
        return response
    
    def generate_detailed_pdf(start_date, end_date, start_str, end_str):
        # Get payments in date range
        payments = Payment.query.filter(
            Payment.payment_date >= start_date,
            Payment.payment_date <= end_date
        ).order_by(Payment.payment_date).all()
        
        # Create PDF
        buffer = io.BytesIO()
        doc = SimpleDocTemplate(buffer, pagesize=letter)
        elements = []
        
        # Get styles
        styles = getSampleStyleSheet()
        title_style = styles['h1']
        heading_style = styles['h2']
        normal_style = styles['Normal']
        
        # Add title
        elements.append(Paragraph("Lavisco Ministers Saving Scheme - Detailed Report", title_style))
        elements.append(Spacer(1, 12))
        
        # Add date range
        elements.append(Paragraph(f"Period: {start_date} to {end_date}", normal_style))
        elements.append(Spacer(1, 12))
        
        # Add payment details
        elements.append(Paragraph("Payment Details", heading_style))
        elements.append(Spacer(1, 6))
        
        payment_data = [['Date', 'Minister Name', 'Amount', 'Week Number', 'Note']]
        
        for payment in payments:
            payment_data.append([
                payment.payment_date.strftime('%Y-%m-%d'),
                payment.minister.full_name,
                f'${payment.amount:.2f}',
                str(payment.week_number) if payment.week_number else '',
                payment.note or ''
            ])
        
        payment_table = Table(payment_data, colWidths=[1*inch, 2*inch, 1*inch, 1*inch, 2*inch])
        payment_table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), colors.grey),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
            ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (-1, 0), 10),
            ('BOTTOMPADDING', (0, 0), (-1, 0), 12),
            ('BACKGROUND', (0, 1), (-1, -1), colors.beige),
            ('GRID', (0, 0), (-1, -1), 1, colors.black),
            ('FONTSIZE', (0, 1), (-1, -1), 8)
        ]))
        
        elements.append(payment_table)
        
        # Build PDF
        doc.build(elements)
        
        buffer.seek(0)
        response = make_response(buffer.getvalue())
        response.headers['Content-Disposition'] = f'attachment; filename=detailed_report_{start_str}_to_{end_str}.pdf'
        response.headers['Content-type'] = 'application/pdf'
        return response
    
    @app.route('/profile', methods=['GET', 'POST'])
    @login_required
    def profile():
        form = ChangePasswordForm()
        if form.validate_on_submit():
            if current_user.check_password(form.current_password.data):
                current_user.set_password(form.new_password.data)
                db.session.commit()
                flash('Your password has been changed successfully!', 'success')
                return redirect(url_for('dashboard'))
            else:
                flash('Current password is incorrect', 'danger')
        
        return render_template('profile.html', title='Profile', form=form)
    
    @app.errorhandler(404)
    def not_found_error(error):
        return render_template('404.html'),