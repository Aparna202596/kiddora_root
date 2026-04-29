# Kiddora 👶👕🛍️

**Kiddora** is a full-featured **monolithic Django-based e-commerce web application** built for **kids’ clothing (Newborn to 15 years)**. It is designed as a production-ready online shopping platform with secure authentication, robust admin management, seamless checkout, payment gateway integration, offer management, and scalable deployment architecture.

The platform combines both **frontend and backend in a single Django application**, delivering a complete e-commerce ecosystem with efficient admin workflows and a smooth customer shopping experience.

---

## 🚀 Tech Stack

### Backend
- **Python**
- **Django**
- **Django ORM**
- **PostgreSQL**

### Frontend
- HTML5
- CSS3
- Bootstrap
- JavaScript
- AJAX

### Authentication & Security
- Email OTP Verification
- Social Login (Single Sign-On)
- Forgot Password Flow
- Secure Session Handling
- CSRF Protection
- Role-based Access Control

### Storage & Deployment
- **Cloudinary** – Static / Media file storage
- **AWS EC2** – Deployment & Hosting
- **Gunicorn** – WSGI Application Server
- **Nginx** – Reverse Proxy / Static Serving

### Payment Integration
- **PayPal Sandbox Integration**
- Cash on Delivery (COD)

---

# Key Features

## 1) Admin Module

Kiddora includes a secure and feature-rich **Admin Dashboard** for complete business management.

### User Management
- Secure admin authentication  
- Dashboard access control  
- Block / Unblock users  
- Confirmation prompts before critical actions  
- Backend-powered search  
- Clear search functionality  
- Pagination for large datasets  
- Descending order sorting (latest users first)

---

### Category Management
- Add categories  
- Edit categories  
- Soft delete categories  
- Search categories  
- Clear search button  
- Pagination support  
- Descending sorting order

---

### Product Management
- Add products  
- Edit products
-  Soft delete products  
- Multiple image uploads  
- Image cropping before upload  
- Image resizing for consistency  
- Product presentation optimization  
- Backend search  
- Pagination support

---

### Order & Inventory Management
- Order listing  
- Detailed order management  
- Order status tracking  
- Return approvals  
- Cancellation handling  
- Stock synchronization  
- Inventory management automation

---

### Offer / Coupon / Sales Management
- Coupon creation & control  
- Apply / remove coupon logic  
- Single-use coupon restriction  
- Transparent discount breakdown  
- Dynamic offer calculation  
- Maximum discount prioritization  
- Referral rewards  
- Wallet credit system  
- Sales analytics dashboard

---

# 2) User Module

## Authentication System
- Signup validation  
- Secure login  
- OTP-based registration  
- OTP timer functionality  
- Resend OTP capability  
- Social single sign-on  
- Forgot password recovery flow

---

## Profile Management
- View profile  
- Edit profile  
- Profile image upload  
- Email change verification (OTP / token)  
- Change password  
- Address management:
- Add address
- Edit address
- Delete address

---

## Product Discovery
- Product browsing  
- Advanced search  
- Sorting options  
- Filter combinations  
- Optimized browsing experience

---

## Wishlist & Cart
### Wishlist
- Add to wishlist  
- Remove from wishlist  
- AJAX-powered updates

### Cart
- Add to cart  
- Remove from cart  
- Quantity increment / decrement  
- Stock validation  
- Blocked item restriction  
- Out-of-stock prevention  
- Real-time AJAX updates

---

## Checkout & Payments
- Address selection  
- Order summary  
- Pricing breakdown  
- Coupon application  
- Wallet usage
- Cash on Delivery support
- PayPal payment integration
- Payment success page
- Payment failure page
- Navigation recovery flows

---

## Order Lifecycle
- Order listing
- Detailed order page
- Search orders
- Download invoice
- Cancel order
- Return order
- Return reason capture
- Refund handling
- Wallet credit refunds
- Stock restoration on cancel/return

---

# Core Business Logic

## Discount Engine
Kiddora includes smart discount prioritization:

- Product offers
- Category offers
- Coupons
- Referral benefits
- Wallet credits

System automatically chooses:

**Maximum applicable discount while preserving business rules**

---

## Wallet System
Users receive wallet credits from:

- Returns
- Refunds
- Referral bonuses
- Promotional credits

Wallet can be used during checkout.

---

## Referral System
- Invite rewards
- Referral bonus credits
- Wallet integration

---

## Search & Pagination
Implemented across:

- Users
- Categories
- Products
- Orders

Includes:

- Backend search  
- Clear button  
- Efficient pagination  
- Sorted listing  

---

## Soft Delete Strategy
Used for:

- Categories  
- Products  
- Select business entities  

Benefits:

- Data recovery possible  
- Reporting integrity maintained  
- Prevent accidental permanent deletion  

---

# Architecture

Kiddora follows a **Monolithic Django Architecture**:

Frontend + Backend + Business Logic + Database  
inside a unified Django project.

Advantages:

- Easier deployment
- Centralized business logic
- Faster development cycle
- Simplified maintenance
- Strong ORM integration  

---

# Deployment

Hosted on **AWS EC2**

Deployment stack:

AWS EC2  
→ Nginx  
→ Gunicorn  
→ Django  
→ PostgreSQL  
→ Cloudinary CDN

Features:

- Production-ready hosting
- Static/media offloaded to Cloudinary
- Secure environment configuration
- Scalable infrastructure

---

# Database

**PostgreSQL** is used for:

- Users
- Products
- Categories
- Orders
- Coupons
- Wallet
- Referrals
- Inventory
- Returns / Refunds

Benefits:

- Reliability
- ACID compliance
- Performance
- Scalability

---

# Highlights

✔ Production-ready project  
✔ Full authentication system  
✔ Admin analytics dashboard  
✔ Payment gateway integration  
✔ Wallet + referral system  
✔ Coupons + offers engine  
✔ Inventory synchronization  
✔ Invoice generation  
✔ Return / refund workflows  
✔ AJAX-powered UX  
✔ Cloud deployment on AWS  

---

# Project Status

**Completed ✅**

Kiddora is fully developed with complete **Admin**, **Customer**, **Commerce**, **Payment**, **Order**, and **Analytics** modules.

Ready for production scaling and future feature enhancements.

---

## Author
Developed with Django + PostgreSQL + Cloudinary + AWS ☁️
