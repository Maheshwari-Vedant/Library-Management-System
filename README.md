# Library Management System

This project is a web-based Library Management System built using Flask and SQLAlchemy. It enables librarians and students to manage books, sections, loans, fines, and reservations efficiently. 

## Features

### User Management
- **Registration and Login**: Users can register and log in with unique credentials.
- **Role-based Access**: Users are categorized as 'librarian' or 'student'.
- **Session Handling**: Includes session expiration and "Remember Me" functionality.

### Book Management
- Add, edit, delete, and view books.
- Search books by title with case-insensitive matching.
- Manage book status: Available, Loaned, Reserved, Removed.

### Section Management
- Add, edit, delete, and view sections.
- Associate books with sections.

### Loan and Reservation Management
- Create, renew, and return book loans.
- Manage reservations and convert reservations into loans.

### Fine Management
- Automatically calculate overdue fines.
- Mark fines as paid.

### Dashboard
- Separate dashboards for librarians and students:
  - **Librarian Dashboard**: Overview of books, sections, users, loans, reservations, and outstanding fines.
  - **Student Dashboard**: Overview of personal loans, reservations, and fines.

### Search Functionality
The frontend manages all search functionalities for:
- Books
- Sections
- Users
- Loans
- Reservations
- Fines

## Technology Stack
- **Frontend**: HTML, CSS, Bootstrap, JavaScript (managed externally).
- **Backend**: Python (Flask framework).
- **Database**: SQLite (via SQLAlchemy ORM).
- **Authentication**: JWT for secure token-based authentication.
- **Libraries**: 
  - `Flask`
  - `Flask_SQLAlchemy`
  - `Werkzeug` for password hashing
  - `JWT` for token management

## Installation

### Prerequisites
- Python 3.x installed on your machine.

### Setup
1. Clone the repository:
   ```bash
   git clone <repository-url>
   cd <repository-folder>
   ```
2. Install the dependencies:
   ```bash
   pip install Flask Flask_SQLAlchemy Werkzeug
   ```
3. Set up the database:
   ```bash
   python app.py
   ```
   The application will automatically create `library.db` if it doesn't exist.

4. Run the server:
   ```bash
   python app.py
   ```
5. Access the application at [http://localhost:5000](http://localhost:5000).

