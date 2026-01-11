// Storage key for localStorage
const STORAGE_KEY = 'lifeMilestones';

// Load milestones from localStorage
function loadMilestones() {
    const stored = localStorage.getItem(STORAGE_KEY);
    return stored ? JSON.parse(stored) : [];
}

// Save milestones to localStorage
function saveMilestones(milestones) {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(milestones));
}

// Format date for display
function formatDate(dateString) {
    const date = new Date(dateString);
    const options = { year: 'numeric', month: 'long', day: 'numeric' };
    return date.toLocaleDateString('en-US', options);
}

// Create milestone HTML element
function createMilestoneElement(milestone, index) {
    const div = document.createElement('div');
    div.className = 'milestone-item';
    div.innerHTML = `
        <div class="milestone-content" style="background: ${milestone.color || '#e8dcc8'} !important;">
            <div class="milestone-date">${formatDate(milestone.date)}</div>
            <div class="milestone-title">${escapeHtml(milestone.title)}</div>
            <span class="milestone-category category-${milestone.category}">${milestone.category}</span>
            ${milestone.description ? `<div class="milestone-description">${escapeHtml(milestone.description)}</div>` : ''}
            <button class="btn-delete" onclick="deleteMilestone(${index})">Delete</button>
        </div>
        <div class="milestone-dot"></div>
    `;
    return div;
}

// Escape HTML to prevent XSS
function escapeHtml(text) {
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
}

// Render all milestones
function renderMilestones() {
    const container = document.getElementById('timeline-container');
    const milestones = loadMilestones();

    // Sort milestones by date (oldest first for horizontal timeline)
    milestones.sort((a, b) => new Date(a.date) - new Date(b.date));

    if (milestones.length === 0) {
        container.innerHTML = '<div class="empty-state"><p>No milestones yet. Add your first milestone above!</p></div>';
        return;
    }

    container.innerHTML = '';
    milestones.forEach((milestone, index) => {
        container.appendChild(createMilestoneElement(milestone, index));
    });
}

// Add new milestone
function addMilestone(event) {
    event.preventDefault();

    const title = document.getElementById('milestone-title').value;
    const date = document.getElementById('milestone-date').value;
    const description = document.getElementById('milestone-description').value;
    const category = document.getElementById('milestone-category').value;
    const color = document.getElementById('milestone-color').value;

    const milestone = {
        title,
        date,
        description,
        category,
        color,
        id: Date.now()
    };

    const milestones = loadMilestones();
    milestones.push(milestone);
    saveMilestones(milestones);

    // Reset form
    document.getElementById('milestone-form').reset();
    document.getElementById('milestone-color').value = '#d4b896';

    // Re-render timeline
    renderMilestones();

    // Scroll to timeline
    document.querySelector('.timeline-section').scrollIntoView({ behavior: 'smooth' });
}

// Delete milestone
function deleteMilestone(index) {
    if (confirm('Are you sure you want to delete this milestone?')) {
        const milestones = loadMilestones();

        // Sort to match the display order before deleting
        milestones.sort((a, b) => new Date(a.date) - new Date(b.date));

        milestones.splice(index, 1);
        saveMilestones(milestones);
        renderMilestones();
    }
}

// Initialize app
document.addEventListener('DOMContentLoaded', () => {
    // Render existing milestones
    renderMilestones();

    // Set up form submission
    document.getElementById('milestone-form').addEventListener('submit', addMilestone);

    // Set max date to today for date input
    const today = new Date().toISOString().split('T')[0];
    document.getElementById('milestone-date').setAttribute('max', today);

    // Sidebar toggle functionality
    const sidebar = document.getElementById('sidebar');
    const toggleBtn = document.getElementById('sidebar-toggle');

    toggleBtn.addEventListener('click', () => {
        sidebar.classList.toggle('sidebar-hidden');
    });

    // Close sidebar when clicking outside on mobile
    document.addEventListener('click', (e) => {
        if (window.innerWidth <= 768 &&
            !sidebar.contains(e.target) &&
            !toggleBtn.contains(e.target) &&
            !sidebar.classList.contains('sidebar-hidden')) {
            sidebar.classList.add('sidebar-hidden');
        }
    });
});

// Make deleteMilestone available globally
window.deleteMilestone = deleteMilestone;
