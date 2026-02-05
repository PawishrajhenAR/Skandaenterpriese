// Calendar Component for Date Range Selection
class DateRangeCalendar {
  constructor(containerId, options = {}) {
    this.container = document.getElementById(containerId);
    this.startDate = options.startDate || null;
    this.endDate = options.endDate || null;
    this.onApply = options.onApply || null;
    this.currentMonth = options.currentMonth || new Date().getMonth();
    this.currentYear = options.currentYear || new Date().getFullYear();
    this.selectingStart = true;
    this.tempStartDate = null;
    this.tempEndDate = null;
    
    this.months = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];
    this.daysOfWeek = ['M', 'T', 'W', 'T', 'F', 'S', 'S'];
    
    this.init();
  }
  
  init() {
    this.render();
    this.attachEvents();
  }
  
  render() {
    const calendarHTML = `
      <div class="calendar">
        <div class="calendar__opts">
          <select name="calendar__month" id="calendar__month">
            ${this.months.map((month, idx) => 
              `<option value="${idx}" ${idx === this.currentMonth ? 'selected' : ''}>${month}</option>`
            ).join('')}
          </select>
          <select name="calendar__year" id="calendar__year">
            ${this.generateYearOptions()}
          </select>
        </div>
        <div class="calendar__body">
          <div class="calendar__days">
            ${this.daysOfWeek.map(day => `<div>${day}</div>`).join('')}
          </div>
          <div class="calendar__dates" id="calendar__dates">
            ${this.renderDates()}
          </div>
        </div>
        <div class="calendar__buttons">
          <button class="calendar__button calendar__button--grey" id="calendar__back">Back</button>
          <button class="calendar__button calendar__button--primary" id="calendar__apply">Apply</button>
        </div>
      </div>
    `;
    
    this.container.innerHTML = calendarHTML;
  }
  
  generateYearOptions() {
    const currentYear = new Date().getFullYear();
    const years = [];
    for (let i = currentYear - 5; i <= currentYear + 5; i++) {
      years.push(`<option value="${i}" ${i === this.currentYear ? 'selected' : ''}>${i}</option>`);
    }
    return years.join('');
  }
  
  renderDates() {
    const firstDay = new Date(this.currentYear, this.currentMonth, 1);
    const lastDay = new Date(this.currentYear, this.currentMonth + 1, 0);
    const daysInMonth = lastDay.getDate();
    const startingDayOfWeek = (firstDay.getDay() + 6) % 7; // Monday = 0
    
    let datesHTML = '';
    
    // Previous month's trailing days
    const prevMonth = new Date(this.currentYear, this.currentMonth, 0);
    const daysInPrevMonth = prevMonth.getDate();
    for (let i = startingDayOfWeek - 1; i >= 0; i--) {
      const date = daysInPrevMonth - i;
      datesHTML += `<div class="calendar__date calendar__date--grey"><span>${date}</span></div>`;
    }
    
    // Current month's days
    for (let date = 1; date <= daysInMonth; date++) {
      const dateObj = new Date(this.currentYear, this.currentMonth, date);
      const classes = this.getDateClasses(dateObj, date);
      datesHTML += `<div class="calendar__date ${classes}" data-date="${dateObj.toISOString().split('T')[0]}"><span>${date}</span></div>`;
    }
    
    // Next month's leading days
    const totalCells = 42; // 6 weeks * 7 days
    const remainingCells = totalCells - (startingDayOfWeek + daysInMonth);
    for (let date = 1; date <= remainingCells; date++) {
      datesHTML += `<div class="calendar__date calendar__date--grey"><span>${date}</span></div>`;
    }
    
    return datesHTML;
  }
  
  getDateClasses(dateObj, date) {
    const dateStr = dateObj.toISOString().split('T')[0];
    const classes = [];
    
    if (this.tempStartDate && this.tempEndDate) {
      if (dateStr === this.tempStartDate) {
        classes.push('calendar__date--selected', 'calendar__date--first-date', 'calendar__date--range-start');
      } else if (dateStr === this.tempEndDate) {
        classes.push('calendar__date--selected', 'calendar__date--last-date', 'calendar__date--range-end');
      } else if (dateStr > this.tempStartDate && dateStr < this.tempEndDate) {
        classes.push('calendar__date--selected', 'calendar__date--first-date');
      }
    } else if (this.tempStartDate && dateStr === this.tempStartDate) {
      classes.push('calendar__date--selected', 'calendar__date--first-date', 'calendar__date--range-start');
    }
    
    return classes.join(' ');
  }
  
  attachEvents() {
    // Month/Year change
    document.getElementById('calendar__month').addEventListener('change', (e) => {
      this.currentMonth = parseInt(e.target.value);
      this.updateDates();
    });
    
    document.getElementById('calendar__year').addEventListener('change', (e) => {
      this.currentYear = parseInt(e.target.value);
      this.updateDates();
    });
    
    // Date clicks
    const datesContainer = document.getElementById('calendar__dates');
    datesContainer.addEventListener('click', (e) => {
      const dateElement = e.target.closest('.calendar__date');
      if (!dateElement || dateElement.classList.contains('calendar__date--grey')) return;
      
      const dateStr = dateElement.getAttribute('data-date');
      if (!dateStr) return;
      
      this.handleDateClick(dateStr);
    });
    
    // Buttons
    document.getElementById('calendar__back').addEventListener('click', () => {
      this.close();
    });
    
    document.getElementById('calendar__apply').addEventListener('click', () => {
      this.apply();
    });
  }
  
  handleDateClick(dateStr) {
    if (!this.tempStartDate || (this.tempStartDate && this.tempEndDate)) {
      // Start new selection
      this.tempStartDate = dateStr;
      this.tempEndDate = null;
      this.selectingStart = false;
    } else {
      // Set end date
      if (dateStr < this.tempStartDate) {
        // Swap if end is before start
        this.tempEndDate = this.tempStartDate;
        this.tempStartDate = dateStr;
      } else {
        this.tempEndDate = dateStr;
      }
    }
    
    this.updateDates();
  }
  
  updateDates() {
    const datesContainer = document.getElementById('calendar__dates');
    datesContainer.innerHTML = this.renderDates();
  }
  
  apply() {
    if (this.tempStartDate && this.tempEndDate) {
      this.startDate = this.tempStartDate;
      this.endDate = this.tempEndDate;
      
      if (this.onApply) {
        this.onApply(this.startDate, this.endDate);
      }
      
      this.close();
    } else if (this.tempStartDate) {
      // If only start date selected, use it as both
      this.startDate = this.tempStartDate;
      this.endDate = this.tempStartDate;
      
      if (this.onApply) {
        this.onApply(this.startDate, this.endDate);
      }
      
      this.close();
    }
  }
  
  close() {
    if (this.container.parentElement) {
      this.container.parentElement.remove();
    }
  }
  
  static show(triggerElement, startDateFieldId, endDateFieldId) {
    // Create modal overlay
    const modal = document.createElement('div');
    modal.className = 'calendar-modal';
    modal.id = 'calendar-modal';
    
    // Create calendar container
    const container = document.createElement('div');
    container.className = 'calendar-container';
    container.id = 'calendar-container';
    
    modal.appendChild(container);
    document.body.appendChild(modal);
    
    // Get current values from form fields
    const startField = document.getElementById(startDateFieldId);
    const endField = document.getElementById(endDateFieldId);
    
    let startDate = null;
    let endDate = null;
    let currentMonth = new Date().getMonth();
    let currentYear = new Date().getFullYear();
    
    if (startField && startField.value) {
      startDate = startField.value;
      const date = new Date(startDate);
      currentMonth = date.getMonth();
      currentYear = date.getFullYear();
    }
    if (endField && endField.value) {
      endDate = endField.value;
    }
    
    // Create calendar instance
    const calendar = new DateRangeCalendar('calendar-container', {
      startDate: startDate,
      endDate: endDate,
      currentMonth: currentMonth,
      currentYear: currentYear,
      onApply: (start, end) => {
        if (startField) {
          startField.value = start;
          // Trigger change event for form validation
          startField.dispatchEvent(new Event('change', { bubbles: true }));
        }
        if (endField) {
          endField.value = end;
          // Trigger change event for form validation
          endField.dispatchEvent(new Event('change', { bubbles: true }));
        }
      }
    });
    
    // Close on overlay click
    modal.addEventListener('click', (e) => {
      if (e.target === modal) {
        modal.remove();
      }
    });
    
    return calendar;
  }
}

// Initialize calendar triggers when DOM is ready
document.addEventListener('DOMContentLoaded', function() {
  // Find all date input fields with calendar trigger
  document.querySelectorAll('.date-input-trigger').forEach(trigger => {
    trigger.addEventListener('click', function() {
      const startFieldId = this.getAttribute('data-start-field');
      const endFieldId = this.getAttribute('data-end-field');
      
      if (startFieldId && endFieldId) {
        DateRangeCalendar.show(this, startFieldId, endFieldId);
      }
    });
  });
});

