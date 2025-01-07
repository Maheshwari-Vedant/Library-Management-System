from flask import Flask, render_template, request, redirect, url_for, jsonify, make_response, flash, session
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy import func
from werkzeug.security import generate_password_hash, check_password_hash
from functools import wraps
from datetime import datetime, timedelta
import jwt
import uuid
import os


app = Flask(__name__)
app.config['SECRET_KEY'] = 'your_secret_key_here'
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///library.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db = SQLAlchemy(app)



class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    public_id = db.Column(db.String(50), unique=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    password = db.Column(db.String(120), nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)
    user_type = db.Column(db.String(20), nullable=False)  # 'librarian' or 'student'

class Section(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), unique=True, nullable=False)
    description = db.Column(db.Text, nullable=True)

    def __str__(self):
        return self.name

class Book(db.Model):
    isbn = db.Column(db.String(13), primary_key=True, unique=True, nullable=False)  # ISBN is now the primary key
    title = db.Column(db.String(200), nullable=False)
    author = db.Column(db.String(100), nullable=False)
    
    # Replacing available_quantity with status field
    status = db.Column(db.Enum('Available', 'Loaned', 'Reserved', 'Removed', name='book_status'), nullable=False, default='Available')
    
    # Section relationship
    section_id = db.Column(db.Integer, db.ForeignKey('section.id'), nullable=True,default=0)  # Book linked to Section
    section = db.relationship('Section', backref=db.backref('books', lazy=True))

    def __str__(self):
        return f"{self.title} by {self.author} (ISBN: {self.isbn})"


class Loan(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    book_id = db.Column(db.Integer, db.ForeignKey('book.isbn'), nullable=False)
    loan_date = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    due_date = db.Column(db.DateTime, nullable=False)
    return_date = db.Column(db.DateTime)
    is_returned = db.Column(db.Boolean, default=False)

    def is_overdue(self):
        return datetime.utcnow() > self.due_date and not self.is_returned

class Reservation(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    book_id = db.Column(db.Integer, db.ForeignKey('book.isbn'), nullable=False)
    reservation_date = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    is_active = db.Column(db.Boolean, default=True)

class Fine(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    amount = db.Column(db.Float, nullable=False)
    is_paid = db.Column(db.Boolean, default=False)
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)

    def mark_paid(self):
        self.is_paid = True


@app.route('/')
def home():
    update_fines()
    return render_template('index.html')

def token_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        token = session.get('token')
        if not token:
            flash('You need to be logged in to access this page.')
            return redirect(url_for('login'))
        try:
            data = jwt.decode(token, app.config['SECRET_KEY'], algorithms=["HS256"])
            current_user = User.query.filter_by(public_id=data['public_id']).first()
        except:
            flash('Invalid token. Please log in again.')
            return redirect(url_for('login'))
        return f(current_user, *args, **kwargs)
    return decorated

def librarian_required(f):
    @wraps(f)
    def decorated(current_user, *args, **kwargs):
        if current_user.user_type != 'librarian':
            flash('Librarian privileges required!')
            return redirect(url_for('home'))
        return f(current_user, *args, **kwargs)
    return decorated


@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        auth = request.form
        username = auth.get('username')
        password = auth.get('password')
        remember_me = request.form.get('rememberMe')  # Get the remember me checkbox value
        
        user = User.query.filter_by(username=username).first()
        if not user or not check_password_hash(user.password, password):
            flash('Login failed. Check your credentials and try again.',"error")
            return redirect(url_for('login'))
        
        token = jwt.encode({
            'public_id': user.public_id,
            'exp': datetime.utcnow() + timedelta(minutes=30)
        }, app.config['SECRET_KEY'], algorithm="HS256")
        
        session['token'] = token
        session['user_type'] = user.user_type  # Store user type to manage UI behavior
        
        # Set session duration based on "Remember Me" checkbox
        if remember_me:
            # Set cookie to expire in 7 days
            session.permanent = True
            app.permanent_session_lifetime = timedelta(days=7)
        else:
            session.permanent = False  # Default session lifetime (browser close)

        if user.user_type == 'student':
            return redirect(url_for('student_dashboard', username=user.username))
        else:
            return redirect(url_for('librarian_dashboard'))
    
    return render_template('login.html')


@app.route('/logout')
def logout():
    session.pop('token', None)
    session.pop('user_type', None)
    flash('You have been logged out.','error')
    return redirect(url_for('login'))

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        data = request.form
        username = data['username']
        email = data['email']
        password = data['password']
        confirm_password = data['confirm_password']
        user_type = data['user_type']

        # Check if passwords match
        if password != confirm_password:
            flash('Passwords do not match. Please try again.',"error")
            return redirect(url_for('register'))

        # Check if the username or email already exists
        existing_user = User.query.filter((User.username == username) | (User.email == email)).first()
        if existing_user:
            flash('Username or email already exists. Please choose another.',"error")
            return redirect(url_for('register'))

        hashed_password = generate_password_hash(password)
        new_user = User(public_id=str(uuid.uuid4()), username=username, password=hashed_password, email=email, user_type=user_type)
        db.session.add(new_user)
        db.session.commit()
        flash('New user created successfully!', 'success')
        return redirect(url_for('login'))

    return render_template('register.html')




@app.route('/librarian_dashboard')
def librarian_dashboard():
    # Get statistics from the database
    total_books = Book.query.count()
    total_sections = Section.query.count()
    total_users = User.query.count()
    books_loaned = Loan.query.filter_by(is_returned=False).count()  # Only count active loans
    books_reserved = Reservation.query.filter_by(is_active=True).count()  # Only active reservations
    outstanding_fines = db.session.query(db.func.sum(Fine.amount)).filter_by(is_paid=False).scalar() or 0  # Sum of unpaid fines

    books = Book.query.all()
    sections = Section.query.filter(Section.id != 0).all()
    loans = Loan.query.all()
    users = User.query.all()
    reserved_books=Reservation.query.all()

    user_dict = {user.id: user.username for user in users}
    book_dict = {book.isbn: book.title for book in books}
    current_time = datetime.utcnow() 
    fines = Fine.query.all()  # Fetch all fines from the database
    

    return render_template('librarian_dashboard.html', 
                           total_books=total_books, 
                           total_sections=total_sections,
                           total_users=total_users, 
                           books_loaned=books_loaned,
                           books_reserved=books_reserved,
                           
                           outstanding_fines=outstanding_fines,books=books,sections=sections,loans=loans,users=users,user_dict=user_dict, book_dict=book_dict, current_time=current_time,reserved_books=reserved_books,fines=fines)



@app.route('/student_dashboard/<username>')
def student_dashboard(username):
    user = User.query.filter_by(username=username).first_or_404()

    # Count the total loans, reservations, and fines for the logged-in user
    total_loans = Loan.query.filter_by(user_id=user.id).count()
    total_reserved = Reservation.query.filter_by(user_id=user.id).count()
    total_fines = db.session.query(db.func.sum(Fine.amount)).filter_by(user_id=user.id, is_paid=False).scalar() or 0

    loans = Loan.query.filter_by(user_id=user.id).all()
    reserves = Reservation.query.filter_by(user_id=user.id).all()
    current_time = datetime.utcnow()


    books = Book.query.all()
    users = User.query.all()
    sections = Section.query.filter(Section.id != 0).all()

    # Get all available books
    available_books = Book.query.filter_by(status='Available').all()
    user_dict = {user.id: user.username for user in users}
    book_dict = {book.isbn: book.title for book in books}

    return render_template(
        'student_dashboard.html',
        total_loans=total_loans,
        total_reserved=total_reserved,
        total_fines=total_fines,
        loans=loans,
        reserves=reserves,
        available_books=available_books,
        current_time=current_time,
        username=username ,user_dict=user_dict, book_dict=book_dict,sections=sections # Pass the username
    )


@app.route('/reserve_book/<username>', methods=['POST'])
def reserve_book(username):
    user = User.query.filter_by(username=username).first_or_404()
    book_id = request.form.get('book_id')  # Get the book's ISBN
    book = Book.query.filter_by(isbn=book_id).first_or_404()  # Query book by ISBN

    # Check if the book is available
    if book.status != 'Available':
        flash('This book is already reserved.', 'error')
        return redirect(url_for('student_dashboard', username=username))

    # Create a reservation
    reservation = Reservation(user_id=user.id, book_id=book.isbn)  # Use isbn instead of id
    db.session.add(reservation)
    book.status = 'Reserved'  # Change book status to Reserved
    db.session.commit()

    flash('Book reserved successfully!', 'success')
    return redirect(url_for('student_dashboard', username=username))



@app.route('/add_book', methods=['GET', 'POST'])
@token_required
@librarian_required
def add_book(current_user):
    if request.method == 'POST':
        title = request.form['title']
        author = request.form['author']
        isbn = request.form['isbn']
        section_id = request.form['section_id'] if request.form['section_id'] else 0
        status = 'Available'

        new_book = Book(title=title, author=author, isbn=isbn, section_id=section_id, status=status)
        db.session.add(new_book)
        db.session.commit()

        flash('Book added successfully!', 'success')  # Flash success message
        return redirect(url_for('librarian_dashboard'))  # Redirect to the dashboard

    sections = Section.query.all()
    return render_template('add_book.html', sections=sections)





@app.route('/edit_book/<string:book_id>', methods=['GET'])
def edit_book(book_id):
    # Fetch the book by its ISBN
    book = Book.query.get(book_id)
    
    # Fetch all available sections
    sections = Section.query.all()

    if book:
        return render_template('edit_book.html', book=book, sections=sections)
    else:
        # Handle case if book is not found
        flash("Book not found!", "danger")
        return redirect(url_for('librarian_dashboard'))


@app.route('/save_edited_book/<string:book_id>', methods=['POST'])
def save_edited_book(book_id):
    # Fetch the book by its ISBN
    book = Book.query.get(book_id)

    if book:
        # Get form data and update book details
        book.title = request.form['title']
        book.author = request.form['author']
        # Use .get() method to avoid KeyError and default to 0 if not selected
        book.section_id = int(request.form.get('section_id', 0))  # Default to 0

        # Save the changes
        db.session.commit()

        # Flash success message
        flash("Book details updated successfully!", "success")

        # Redirect back to the dashboard
        return redirect(url_for('librarian_dashboard'))
    else:
        # Handle case if book is not found
        flash("Book not found!", "danger")
        return redirect(url_for('librarian_dashboard'))

@app.route('/delete_book/<string:book_id>', methods=['POST'])
def delete_book(book_id):
    # Fetch the book by its ISBN
    book = Book.query.get(book_id)

    if book:
        # Delete the book from the database
        db.session.delete(book)
        db.session.commit()

        # Flash success message
        flash("Book deleted successfully!", "success")
    else:
        # Handle case if book is not found
        flash("Book not found!", "danger")

    # Redirect back to the dashboard
    return redirect(url_for('librarian_dashboard'))





@app.route('/add_section', methods=['GET', 'POST'])
@token_required
@librarian_required
def add_section(current_user):
    if request.method == 'POST':
        section_name = request.form['section_name']
        section_description = request.form['section_description']
        selected_books = request.form.getlist('selected_books')  # Get selected books
        
        # Validate inputs
        if not section_name or not section_description:
            flash('Section name and description are required.', 'danger')
            return redirect(url_for('add_section'))

        # Create new section
        new_section = Section(name=section_name, description=section_description)
        
        try:
            db.session.add(new_section)
            db.session.commit()
            
            # Associate selected books with the new section
            for book_isbn in selected_books:
                book = Book.query.filter_by(isbn=book_isbn).first()
                if book:
                    book.section_id = new_section.id  # Update book's section_id

            db.session.commit()  # Commit once after updating all books

            flash('Section added successfully!', 'success')
            return redirect(url_for('librarian_dashboard'))

        except Exception as e:
            db.session.rollback()  # Rollback in case of error
            flash('An error occurred while adding the section.', 'danger')
            return redirect(url_for('librarian_dashboard'))
    
    # GET request: Query for books with section_id = 0 or NULL
    books = Book.query.filter((Book.section_id == 0) | (Book.section_id.is_(None))).all()
    
    return render_template('add_section.html', books=books)



@app.route('/edit_section/<int:section_id>', methods=['GET', 'POST'])
# @token_required
# @librarian_required
def edit_section(section_id):
    section = Section.query.get_or_404(section_id)

    if request.method == 'POST':
        section.name = request.form['name']
        section.description = request.form['description']
        
        # Get selected book ISBNs from the form
        selected_books = request.form.getlist('books')

        # Update section's books
        # Clear existing books linked to this section
        for book in section.books:
            book.section_id = 0  # Unlink book from section by setting to 0

        for isbn in selected_books:
            book = Book.query.filter_by(isbn=isbn).first()
            if book:
                book.section_id = section.id  # Link book to the section

        db.session.commit()
        flash('Section updated successfully!', 'success')
        return redirect(url_for('librarian_dashboard'))

    # Get books that are either in this section or have a section_id of 0
    books = Book.query.filter((Book.section_id == section.id) | (Book.section_id == 0)).all()

    return render_template('edit_section.html', section=section, books=books)





@app.route('/view_section/<section_id>')
def view_section(section_id):
    section = Section.query.get(section_id)
    books = Book.query.filter_by(section_id=section_id).all()
    # Capture username for student dashboard context
    username = request.args.get('username') 
    return render_template('view_section.html', section=section, books=books, username=username)


@app.route('/view_section_lib/<int:section_id>', methods=['GET'])
# @token_required
# @librarian_required
def view_section_lib(section_id):
    section = Section.query.get_or_404(section_id)  # Fetch the section by ID
    books = Book.query.filter_by(section_id=section.id).all()  # Fetch all books in that section
    return render_template('view_section_lib.html', section=section, books=books)



@app.route('/delete_section/<int:section_id>', methods=['POST'])
# @token_required
# @librarian_required
def delete_section(section_id):
    section = Section.query.get_or_404(section_id)

    # Set section_id of all books in this section to 0 before deleting the section
    books_in_section = Book.query.filter_by(section_id=section.id).all()
    for book in books_in_section:
        book.section_id = 0  # Unlink book from section by setting to 0

    db.session.delete(section)

    try:
        db.session.commit()  # Commit the changes
        flash('Section deleted successfully!', 'success')
    except Exception as e:
        db.session.rollback()
        print(f"Error occurred: {e}")
        flash('An error occurred while deleting the section. Please try again.', 'error')

    return redirect(url_for('librarian_dashboard'))



@app.route('/search_books')
def search_books():
    query = request.args.get('q', '')
    books = Book.query.filter(Book.title.ilike(f'%{query}%')).all()
    
    book_list = [{'id': book.id, 'title': book.title, 'author': book.author} for book in books]
    return jsonify(book_list)

from datetime import datetime

@app.route('/add_loan', methods=['GET', 'POST'])
def add_loan():
    if request.method == 'POST':
        # Get the selected user and book from the form
        selected_user_id = request.form.get('selected_user')
        selected_book_isbn = request.form.get('selected_book')

        # Fetch the user and book from the database
        user = User.query.get(selected_user_id)
        book = Book.query.filter_by(isbn=selected_book_isbn).first()

        # Validate if both user and book are selected
        if not user or not book:
            flash('Please select a valid user and book.', 'danger')
            return redirect(url_for('add_loan'))

        # Check if the book is available
        if book.status != 'Available':
            flash('The selected book is not available.', 'danger')
            return redirect(url_for('add_loan'))

        # Create a new loan record
        new_loan = Loan(
            user_id=user.id,         # Assuming `user.id` is correct
            book_id=book.isbn,      # Use book.isbn for book_id
            due_date=calculate_due_date()  # Ensure this function is defined to return a datetime
        )
        db.session.add(new_loan)

        # Update the book status to 'Loaned'
        book.status = 'Loaned'
        db.session.commit()

        # Flash a success message and redirect to the dashboard
        flash('Loan created successfully!', 'success')
        return redirect(url_for('librarian_dashboard'))

    # Fetch users with the role 'student' and only books that have the status 'Available'
    users = User.query.filter_by(user_type='student').all()  # Only fetch students
    books = Book.query.filter_by(status='Available').all()  # Only fetch available books

    return render_template('add_loan.html', users=users, books=books)

def calculate_due_date():
    """Utility function to calculate a due date for the loan."""
    from datetime import datetime, timedelta
    return datetime.utcnow() + timedelta(days=14)  # Example: 14 days loan period


@app.route('/renew_loan/<int:loan_id>', methods=['POST'])
def renew_loan(loan_id):
    # Fetch the loan by ID
    loan = Loan.query.get(loan_id)
    if not loan:
        flash('Loan not found.', 'danger')
        return redirect(url_for('dashboard'))  # Adjust according to your route

    # Update the loan dates
    loan.loan_date = datetime.now()  # Set the current date as loan_date
    loan.due_date = loan.loan_date + timedelta(days=14)  # Set due_date to 14 days from loan_date

    # Commit the changes to the database
    db.session.commit()
    
    flash('Loan renewed successfully!', 'success')
    return redirect(url_for('librarian_dashboard')) 

@app.route('/return_loan/<int:loan_id>', methods=['POST'])
def return_loan(loan_id):
    # Fetch the loan by ID
    loan = Loan.query.get(loan_id)
    if not loan:
        flash('Loan not found.', 'danger')
        return redirect(url_for('dashboard'))  # Adjust according to your route

    # Fetch the corresponding book
    book = Book.query.get(loan.book_id)
    if not book:
        flash('Book not found.', 'danger')
        return redirect(url_for('dashboard'))  # Adjust according to your route

    # Update the book's status to available
    book.status = 'Available'

    # Delete the loan entry
    db.session.delete(loan)

    # Commit the changes to the database
    db.session.commit()
    
    flash('Loan returned successfully! Book status updated to available.', 'success')
    return redirect(url_for('librarian_dashboard'))  # Redirect to the dashboard or relevant page

@app.route('/loan_book/<int:reserve_id>', methods=['POST'])
def loan_book(reserve_id):
    # Get the reservation entry from the database
    reservation = Reservation.query.get(reserve_id)
    
    if reservation:
        # Get the associated book
        book = Book.query.get(reservation.book_id)
        
        if book and book.status == 'Reserved':
            # Update the book status to 'Loaned'
            book.status = 'Loaned'
            
            # Create a new loan entry
            new_loan = Loan(user_id=reservation.user_id, book_id=book.isbn, due_date=calculate_due_date())  # Assuming a function to calculate due date
            db.session.add(new_loan)
            
            # Remove the reservation entry
            db.session.delete(reservation)
            
            # Commit the changes to the database
            db.session.commit()
            
            flash('Book successfully loaned!', 'success')
        else:
            flash('This book cannot be loaned at the moment.', 'danger')
    else:
        flash('Reservation not found.', 'danger')

    return redirect(url_for('librarian_dashboard'))

from datetime import datetime

@app.route('/view_user/<int:user_id>', methods=['GET'])
def view_user(user_id):
    user = User.query.get(user_id)
    if not user:
        return "User not found", 404

    # Get loans for the user
    loans = Loan.query.filter_by(user_id=user_id).all()

    # Calculate total fines (based on overdue loans)
    overdue_fine_per_day = 1.0  # For example, a fine of 1 unit per day overdue
    total_fines = 0.0
    for loan in loans:
        if loan.is_overdue():
            overdue_days = (datetime.utcnow() - loan.due_date).days
            total_fines += overdue_days * overdue_fine_per_day

    # Get fines from the Fine table
    fines = Fine.query.filter_by(user_id=user_id, is_paid=False).all()
    total_fine_from_db = sum(fine.amount for fine in fines)

    # Reserved books
    reservations = Reservation.query.filter_by(user_id=user_id, is_active=True).all()

    return render_template('view_user.html', user=user, loans=loans, reservations=reservations, 
                           total_fines=total_fines + total_fine_from_db, fines=fines)



@app.route('/reservation/add', methods=['POST'])
@token_required
@librarian_required
def add_reservation(current_user):
    data = request.form
    new_reservation = Reservation(
        user_id=data['user_id'],
        book_id=data['book_id']
    )
    db.session.add(new_reservation)
    db.session.commit()
    flash('Reservation added successfully!')
    return redirect(url_for('librarian_dashboard'))

@app.route('/reservation/cancel/<int:reservation_id>', methods=['POST'])
@token_required
@librarian_required
def cancel_reservation(current_user, reservation_id):
    reservation = Reservation.query.get_or_404(reservation_id)
    reservation.is_active = False
    db.session.commit()
    flash('Reservation cancelled successfully!')
    return redirect(url_for('librarian_dashboard'))



@app.route('/mark_fine_paid/<int:fine_id>', methods=['POST'])
def mark_fine_paid(fine_id):
    fine = Fine.query.get(fine_id)
    if fine and not fine.is_paid:
        fine.is_paid = True  # Mark fine as paid
        db.session.commit()
        flash('Fine marked as paid successfully.', 'success')
    else:
        flash('Fine not found or already paid.', 'danger')
    return redirect(url_for('librarian_dashboard'))





def update_fines():
    Fine.query.delete()
    db.session.commit() 
    # Get the current date
    current_date = datetime.utcnow()

    # Query all loans that are overdue
    overdue_loans = Loan.query.filter(Loan.due_date < current_date, Loan.is_returned == False).all()

    # Iterate over each overdue loan and create a fine entry
    for loan in overdue_loans:
        # Calculate the number of days overdue
        days_overdue = (current_date - loan.due_date).days
        
        # Calculate the fine amount ($1 per day)
        fine_amount = days_overdue * 1.0  # Adjust the fine rate if necessary

        # Check if a fine already exists for this user and loan
        existing_fine = Fine.query.filter_by(user_id=loan.user_id, is_paid=False).first()

        if existing_fine:
            # If a fine already exists, update the amount
            existing_fine.amount += fine_amount
        else:
            # Otherwise, create a new fine entry
            new_fine = Fine(user_id=loan.user_id, amount=fine_amount)
            db.session.add(new_fine)

    # Commit the session to save changes
    db.session.commit()



if __name__ == '__main__':
    # Check if the database exists, create if it does not
    if not os.path.exists('library.db'):
        with app.app_context():
            db.create_all()  # Create database and tables
    app.run(debug=True)
    
