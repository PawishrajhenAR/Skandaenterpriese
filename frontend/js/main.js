// Main JavaScript for Skanda Credit & Billing System

document.addEventListener('DOMContentLoaded', function() {
    // Initialize toast notifications
    const toastElements = document.querySelectorAll('.toast');
    toastElements.forEach(function(toastEl) {
        // Ensure each toast only shows once
        if (toastEl.classList.contains('showing') || toastEl.classList.contains('show')) {
            return;
        }
        
        const toast = new bootstrap.Toast(toastEl, {
            autohide: true,
            delay: 4000
        });
        
        // Show toast with smooth animation
        setTimeout(function() {
            toast.show();
        }, 100);
        
        // Remove toast element from DOM after it's hidden
        toastEl.addEventListener('hidden.bs.toast', function() {
            toastEl.remove();
        });
    });
    
    // Form validation enhancement
    const forms = document.querySelectorAll('form');
    forms.forEach(function(form) {
        form.addEventListener('submit', function(event) {
            if (!form.checkValidity()) {
                event.preventDefault();
                event.stopPropagation();
            }
            form.classList.add('was-validated');
        }, false);
    });
    
    // Initialize table sorting
    initTableSorting();
    
    // Initialize tooltips
    const tooltipTriggerList = [].slice.call(document.querySelectorAll('[data-bs-toggle="tooltip"]'));
    tooltipTriggerList.map(function (tooltipTriggerEl) {
        return new bootstrap.Tooltip(tooltipTriggerEl);
    });
    
    // Initialize popovers
    const popoverTriggerList = [].slice.call(document.querySelectorAll('[data-bs-toggle="popover"]'));
    popoverTriggerList.map(function (popoverTriggerEl) {
        return new bootstrap.Popover(popoverTriggerEl);
    });
    
    // Mobile menu toggle (Updated for new design)
    const sidebarToggle = document.querySelector('.sidebar-toggle');
    const sidebar = document.querySelector('.app-sidebar');
    
    if (sidebarToggle && sidebar) {
        sidebarToggle.addEventListener('click', function() {
            sidebar.classList.toggle('show');
        });
        
        // Close sidebar when clicking outside on mobile
        document.addEventListener('click', function(event) {
            const isClickInsideSidebar = sidebar.contains(event.target);
            const isClickOnToggle = sidebarToggle.contains(event.target);
            
            if (window.innerWidth <= 768 && !isClickInsideSidebar && !isClickOnToggle && sidebar.classList.contains('show')) {
                sidebar.classList.remove('show');
            }
        });
    }
    
    // Smooth scroll for anchor links
    document.querySelectorAll('a[href^="#"]').forEach(anchor => {
        anchor.addEventListener('click', function (e) {
            const href = this.getAttribute('href');
            if (href !== '#' && href.length > 1) {
                e.preventDefault();
                const target = document.querySelector(href);
                if (target) {
                    target.scrollIntoView({
                        behavior: 'smooth',
                        block: 'start'
                    });
                }
            }
        });
    });
});

// Table Sorting Functionality
function initTableSorting() {
    const sortableHeaders = document.querySelectorAll('.table thead th.sortable');
    
    sortableHeaders.forEach(header => {
        header.addEventListener('click', function() {
            const table = this.closest('table');
            const tbody = table.querySelector('tbody');
            const rows = Array.from(tbody.querySelectorAll('tr'));
            const columnIndex = Array.from(this.parentElement.children).indexOf(this);
            const isAscending = this.classList.contains('sort-asc');
            
            // Remove sort classes from all headers
            sortableHeaders.forEach(h => {
                h.classList.remove('sort-asc', 'sort-desc');
            });
            
            // Add appropriate sort class
            this.classList.add(isAscending ? 'sort-desc' : 'sort-asc');
            
            // Sort rows
            rows.sort((a, b) => {
                const aText = a.children[columnIndex].textContent.trim();
                const bText = b.children[columnIndex].textContent.trim();
                
                // Try to parse as number
                const aNum = parseFloat(aText.replace(/[₹,]/g, ''));
                const bNum = parseFloat(bText.replace(/[₹,]/g, ''));
                
                if (!isNaN(aNum) && !isNaN(bNum)) {
                    return isAscending ? bNum - aNum : aNum - bNum;
                }
                
                // Compare as strings
                return isAscending 
                    ? bText.localeCompare(aText)
                    : aText.localeCompare(bText);
            });
            
            // Reorder rows in DOM
            rows.forEach(row => tbody.appendChild(row));
        });
    });
}

// Debounce function for search inputs
function debounce(func, wait) {
    let timeout;
    return function executedFunction(...args) {
        const later = () => {
            clearTimeout(timeout);
            func(...args);
        };
        clearTimeout(timeout);
        timeout = setTimeout(later, wait);
    };
}

// Debounced search function
const debouncedSearch = debounce(function(input) {
    const form = input.closest('form');
    if (form) {
        form.submit();
    }
}, 500);

// Make debouncedSearch available globally
window.debounceSearch = debouncedSearch;

// Filter management
function clearAllFilters() {
    window.location.href = window.location.pathname;
}

function removeFilter(key) {
    const url = new URL(window.location);
    url.searchParams.delete(key);
    url.searchParams.delete(key + '_from');
    url.searchParams.delete(key + '_to');
    url.searchParams.delete(key + '_min');
    url.searchParams.delete(key + '_max');
    window.location.href = url.toString();
}

// Helper function for number formatting
function formatCurrency(amount) {
    return '₹' + parseFloat(amount).toFixed(2).replace(/\B(?=(\d{3})+(?!\d))/g, ",");
}

// Helper function for date formatting
function formatDate(dateString) {
    const date = new Date(dateString);
    return date.toLocaleDateString('en-IN', {
        year: 'numeric',
        month: 'short',
        day: 'numeric'
    });
}

// Add loading spinner
function showLoading() {
    const spinner = document.createElement('div');
    spinner.className = 'spinner-overlay';
    spinner.innerHTML = '<div class="spinner"></div>';
    document.body.appendChild(spinner);
}

function hideLoading() {
    const spinner = document.querySelector('.spinner-overlay');
    if (spinner) {
        spinner.remove();
    }
}

// Form submission with loading
document.addEventListener('submit', function(e) {
    const form = e.target;
    // Don't show loading for filter forms on input change (handled by debounce)
    // or if explicitly opted out
    if (form.tagName === 'FORM' && !form.classList.contains('no-loading') && e.submitter) {
         showLoading();
    }
});

// Dynamic bill items management (if on bill form page)
if (document.getElementById('bill-items-container')) {
    let itemCount = document.querySelectorAll('.bill-item-row').length || 1;
    
    window.addBillItem = function() {
        const container = document.getElementById('bill-items-container');
        const template = document.getElementById('bill-item-template');
        const newItem = template.content.cloneNode(true);
        
        // Update input names with new index
        newItem.querySelectorAll('input, select').forEach(input => {
            const name = input.getAttribute('name');
            if (name) {
                input.setAttribute('name', name.replace('[0]', `[${itemCount}]`));
                input.setAttribute('id', input.getAttribute('id')?.replace('_0', `_${itemCount}`) || '');
            }
        });
        
        container.appendChild(newItem);
        itemCount++;
        updateBillTotal();
    };
    
    window.removeBillItem = function(button) {
        const row = button.closest('.bill-item-row');
        if (row) {
            row.remove();
            updateBillTotal();
        }
    };
    
    window.updateBillTotal = function() {
        let subtotal = 0;
        document.querySelectorAll('.bill-item-row').forEach(row => {
            const quantity = parseFloat(row.querySelector('[name*="quantity"]')?.value || 0);
            const price = parseFloat(row.querySelector('[name*="unit_price"]')?.value || 0);
            const amount = quantity * price;
            subtotal += amount;
            
            const amountInput = row.querySelector('[name*="amount"]');
            if (amountInput) {
                amountInput.value = amount.toFixed(2);
            }
        });
        
        const taxRate = parseFloat(document.getElementById('tax_rate')?.value || 0);
        const tax = subtotal * (taxRate / 100);
        const total = subtotal + tax;
        
        document.getElementById('subtotal-display').textContent = formatCurrency(subtotal);
        document.getElementById('tax-display').textContent = formatCurrency(tax);
        document.getElementById('total-display').textContent = formatCurrency(total);
        
        const totalInput = document.getElementById('amount_total');
        if (totalInput) {
            totalInput.value = total.toFixed(2);
        }
    };
    
    // Add event listeners to quantity and price inputs
    document.addEventListener('input', function(e) {
        if (e.target.matches('[name*="quantity"], [name*="unit_price"]')) {
            updateBillTotal();
        }
    });
}

// Export functions globally
window.clearAllFilters = clearAllFilters;
window.removeFilter = removeFilter;

// ============================================
// PWA (Progressive Web App) Support
// ============================================

// Register Service Worker
if ('serviceWorker' in navigator) {
    window.addEventListener('load', () => {
        navigator.serviceWorker.register('/service-worker.js')
            .then((registration) => {
                console.log('Service Worker registered successfully:', registration.scope);
                
                // Check for updates periodically
                setInterval(() => {
                    registration.update();
                }, 60000); // Check every minute
            })
            .catch((error) => {
                console.log('Service Worker registration failed:', error);
            });
        
        // Listen for service worker updates
        navigator.serviceWorker.addEventListener('controllerchange', () => {
            console.log('New service worker activated. Reloading page...');
            window.location.reload();
        });
    });
}

// PWA Install Prompt
let deferredPrompt;
const installButton = document.getElementById('pwa-install-button');

window.addEventListener('beforeinstallprompt', (e) => {
    // Prevent the mini-infobar from appearing on mobile
    e.preventDefault();
    // Stash the event so it can be triggered later
    deferredPrompt = e;
    
    // Show custom install button if it exists
    if (installButton) {
        installButton.style.display = 'block';
        installButton.addEventListener('click', () => {
            installButton.style.display = 'none';
            // Show the install prompt
            deferredPrompt.prompt();
            // Wait for the user to respond to the prompt
            deferredPrompt.userChoice.then((choiceResult) => {
                if (choiceResult.outcome === 'accepted') {
                    console.log('User accepted the install prompt');
                } else {
                    console.log('User dismissed the install prompt');
                }
                deferredPrompt = null;
            });
        });
    }
});

// Handle successful PWA installation
window.addEventListener('appinstalled', () => {
    console.log('PWA was installed');
    deferredPrompt = null;
    if (installButton) {
        installButton.style.display = 'none';
    }
    // Show success message
    if (typeof showToast === 'function') {
        showToast('App installed successfully!', 'success');
    }
});

// Check if app is already installed
if (window.matchMedia('(display-mode: standalone)').matches || window.navigator.standalone === true) {
    console.log('App is running in standalone mode');
    document.body.classList.add('pwa-standalone');
    if (installButton) {
        installButton.style.display = 'none';
    }
}

// Offline/Online status handling
window.addEventListener('online', () => {
    console.log('Connection restored');
    if (typeof showToast === 'function') {
        showToast('You are back online', 'success');
    } else {
        // Fallback notification
        const notification = document.createElement('div');
        notification.className = 'alert alert-success alert-dismissible fade show position-fixed top-0 start-50 translate-middle-x mt-3';
        notification.style.zIndex = '9999';
        notification.innerHTML = '<i class="bi bi-wifi me-2"></i>You are back online<button type="button" class="btn-close" data-bs-dismiss="alert"></button>';
        document.body.appendChild(notification);
        setTimeout(() => notification.remove(), 3000);
    }
});

window.addEventListener('offline', () => {
    console.log('Connection lost');
    if (typeof showToast === 'function') {
        showToast('You are offline. Some features may be limited.', 'warning');
    } else {
        // Fallback notification
        const notification = document.createElement('div');
        notification.className = 'alert alert-warning alert-dismissible fade show position-fixed top-0 start-50 translate-middle-x mt-3';
        notification.style.zIndex = '9999';
        notification.innerHTML = '<i class="bi bi-wifi-off me-2"></i>You are offline. Some features may be limited.<button type="button" class="btn-close" data-bs-dismiss="alert"></button>';
        document.body.appendChild(notification);
    }
});

// Helper function to show toast (if not already defined)
if (typeof showToast === 'undefined') {
    window.showToast = function(message, type = 'info') {
        const toastContainer = document.querySelector('.toast-container') || document.body;
        const toast = document.createElement('div');
        toast.className = `toast align-items-center text-white bg-${type === 'error' ? 'danger' : type} border-0`;
        toast.setAttribute('role', 'alert');
        toast.innerHTML = `
            <div class="d-flex">
                <div class="toast-body">
                    <i class="bi bi-${type === 'success' ? 'check-circle' : type === 'error' || type === 'danger' ? 'exclamation-triangle' : type === 'warning' ? 'exclamation-circle' : 'info-circle'}-fill me-2"></i>
                    ${message}
                </div>
                <button type="button" class="btn-close btn-close-white me-2 m-auto" data-bs-dismiss="toast"></button>
            </div>
        `;
        toastContainer.appendChild(toast);
        const bsToast = new bootstrap.Toast(toast, { autohide: true, delay: 4000 });
        bsToast.show();
        toast.addEventListener('hidden.bs.toast', () => toast.remove());
    };
}