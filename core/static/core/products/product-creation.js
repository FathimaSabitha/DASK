(() => {
  'use strict';

  const form = document.querySelector('#productForm');
  const saveButton = document.querySelector('#saveButton');
  const variantList = document.querySelector('#variantList');
  const toast = document.querySelector('#toast');
  const toastMessage = document.querySelector('#toastMessage');
  const toastIcon = document.querySelector('#toastIcon');
  const currency = new Intl.NumberFormat('en-IN', { style: 'currency', currency: 'INR', minimumFractionDigits: 2 });
  let toastTimer;
  let isDirty = false;
  let variantId = 0;

  const fields = {
    productName: { message: 'Enter a product name.', validate: value => value.trim().length > 0 },
    productType: { message: 'Choose a product type.', validate: value => value !== '' },
    salesPrice: { message: 'Enter a valid sales price of ₹0 or more.', validate: value => value !== '' && Number.isFinite(Number(value)) && Number(value) >= 0 },
    costPrice: { message: 'Enter a valid cost price of ₹0 or more.', validate: value => value !== '' && Number.isFinite(Number(value)) && Number(value) >= 0 },
    productNotes: { message: 'Add product notes so your team has the required context.', validate: value => value.trim().length > 0 }
  };

  const byId = id => document.querySelector(`#${id}`);
  const money = value => value === '' || !Number.isFinite(Number(value)) ? '₹0.00' : currency.format(Number(value));
  const basePrice = () => Math.max(0, Number(byId('salesPrice')?.value) || 0);

  function setFieldValidity(name, showError = true) {
    const element = byId(name);
    if (!element) return true;
    const field = element.closest('.field');
    const error = byId(`${name}Error`);
    let valid = true;

    if (name === 'productType') {
      if (!element.value) {
        valid = false;
        if (error) error.textContent = showError ? fields[name].message : '';
        const customContainer = byId('customTypeContainer');
        if (customContainer) customContainer.classList.remove('is-invalid');
      } else if (element.value === 'Other') {
        const customInput = byId('customProductType');
        const customContainer = byId('customTypeContainer');
        const customError = byId('customProductTypeError');
        const customValid = customInput ? customInput.value.trim().length > 0 : false;
        valid = customValid;
        if (error) error.textContent = '';
        if (customContainer) customContainer.classList.toggle('is-invalid', showError && !customValid);
        if (customInput) customInput.setAttribute('aria-invalid', String(showError && !customValid));
        if (customError) customError.textContent = showError && !customValid ? 'Enter your custom product type.' : '';
      } else {
        valid = true;
        if (error) error.textContent = '';
        const customContainer = byId('customTypeContainer');
        if (customContainer) customContainer.classList.remove('is-invalid');
        const customError = byId('customProductTypeError');
        if (customError) customError.textContent = '';
      }
    } else {
      valid = fields[name].validate(element.value);
      if (error) error.textContent = showError && !valid ? fields[name].message : '';
    }

    if (field) field.classList.toggle('is-invalid', showError && !valid);
    element.setAttribute('aria-invalid', String(showError && !valid));
    return valid;
  }

  function updateCounters() {
    const nameInput = byId('productName');
    const notesInput = byId('productNotes');
    const nameCount = byId('nameCount');
    const notesCount = byId('notesCount');
    if (nameInput && nameCount) nameCount.textContent = `${nameInput.value.length} / 80`;
    if (notesInput && notesCount) notesCount.textContent = `${notesInput.value.length} / 500`;
  }

  function getVariants() {
    return [...document.querySelectorAll('.variant-row')].map(row => ({
      name: row.querySelector('[data-variant-name]')?.value.trim() || '',
      additionalPrice: Math.max(0, Number(row.querySelector('[data-variant-price]')?.value) || 0)
    }));
  }

  function selectedVariant() {
    const rows = [...document.querySelectorAll('.variant-row')];
    return rows.find(row => row.classList.contains('is-selected')) || rows[0] || null;
  }

  function updateVariantRows() {
    const base = basePrice();
    document.querySelectorAll('.variant-row').forEach((row, index) => {
      const price = Math.max(0, Number(row.querySelector('[data-variant-price]')?.value) || 0);
      const indexEl = row.querySelector('[data-variant-index]');
      const totalEl = row.querySelector('[data-variant-total]');
      if (indexEl) indexEl.textContent = `Variant ${index + 1}`;
      if (totalEl) totalEl.textContent = money(base + price);
    });
    const active = selectedVariant();
    const activePrice = active ? Math.max(0, Number(active.querySelector('[data-variant-price]')?.value) || 0) : 0;
    const activeName = active ? active.querySelector('[data-variant-name]')?.value.trim() || 'Selected variant' : '';
    const variantPricePreview = document.querySelector('[data-preview="variantPrice"]');
    const variantPriceLabel = byId('variantPriceLabel');
    if (variantPricePreview) variantPricePreview.textContent = money(base + activePrice);
    if (variantPriceLabel) {
      variantPriceLabel.textContent = active
        ? `${activeName}: ${money(base)} base + ${money(activePrice)} additional price.`
        : 'Add a variant to see its calculated selling price.';
    }
    const empty = byId('variantEmpty');
    if (empty) empty.hidden = document.querySelectorAll('.variant-row').length > 0;
  }

  function getSelectedProductType() {
    const type = byId('productType')?.value || '';
    if (type === 'Other') {
      const custom = byId('customProductType')?.value.trim();
      return custom || 'Other (custom)';
    }
    return type;
  }

  function updatePreview() {
    const name = byId('productName')?.value.trim() || '';
    const type = getSelectedProductType();
    const previewName = document.querySelector('[data-preview="name"]');
    const previewType = document.querySelector('[data-preview="type"]');
    const previewSales = document.querySelector('[data-preview="salesPrice"]');
    const previewCost = document.querySelector('[data-preview="costPrice"]');

    if (previewName) previewName.textContent = name || 'Untitled product';
    if (previewType) previewType.textContent = type || 'Product type';
    if (previewSales) previewSales.textContent = money(byId('salesPrice')?.value || 0);
    if (previewCost) previewCost.textContent = money(byId('costPrice')?.value || 0);
    updateVariantRows();
  }

  function showToast(message, type = 'success') {
    if (!toast || !toastMessage || !toastIcon) return;
    toastMessage.textContent = message;
    toastIcon.textContent = type === 'error' ? '!' : '✓';
    toast.classList.toggle('error', type === 'error');
    toast.classList.add('show');
    window.clearTimeout(toastTimer);
    toastTimer = window.setTimeout(() => toast.classList.remove('show'), 4200);
  }

  function addVariant(name = '', additionalPrice = 0) {
    variantId += 1;
    const row = document.createElement('div');
    row.className = 'variant-row';
    row.dataset.variantId = String(variantId);
    row.innerHTML = `
      <span class="variant-index" data-variant-index>Variant</span>
      <div class="field">
        <label for="variantName-${variantId}">Brand or configuration <em>*</em></label>
        <input id="variantName-${variantId}" name="variant_name" type="text" data-variant-name maxlength="80" placeholder="e.g. Odoo or Professional" value="${escapeHtml(name)}" autocomplete="off" />
        <p class="field-hint">This identifies the product variant.</p>
      </div>
      <div class="field price-field">
        <label for="variantPrice-${variantId}">Additional price</label>
        <div class="currency-input"><span aria-hidden="true">₹</span><input id="variantPrice-${variantId}" name="variant_additional_price" type="number" data-variant-price min="0" step="0.01" value="${Number(additionalPrice) || 0}" /></div>
        <p class="field-hint">Added to the base sales price.</p>
      </div>
      <button class="remove-variant" type="button" aria-label="Remove this variant">×</button>
      <div class="variant-result"><span>Customer price</span><strong data-variant-total>₹0.00</strong></div>
    `;
    variantList.append(row);
    const variantErrorEl = byId('variantListError');
    if (variantErrorEl) variantErrorEl.style.display = 'none';

    row.querySelector('[data-variant-name]').addEventListener('input', () => { isDirty = true; updatePreview(); });
    row.querySelector('[data-variant-price]').addEventListener('input', () => { isDirty = true; updatePreview(); });
    row.addEventListener('click', event => {
      if (event.target.closest('.remove-variant')) return;
      document.querySelectorAll('.variant-row').forEach(item => item.classList.remove('is-selected'));
      row.classList.add('is-selected');
      updatePreview();
    });
    row.querySelector('.remove-variant').addEventListener('click', () => {
      row.remove();
      isDirty = true;
      updatePreview();
    });
    document.querySelectorAll('.variant-row').forEach(item => item.classList.remove('is-selected'));
    row.classList.add('is-selected');
    updatePreview();
    row.querySelector('[data-variant-name]').focus();
  }

  function escapeHtml(value) {
    return String(value).replace(/[&<>'"]/g, character => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', "'": '&#39;', '"': '&quot;' })[character]);
  }

  Object.keys(fields).forEach(name => {
    const element = byId(name);
    if (!element) return;
    element.addEventListener('input', () => {
      isDirty = true;
      updateCounters();
      updatePreview();
      if (element.closest('.field')?.classList.contains('is-invalid')) setFieldValidity(name);
    });
    element.addEventListener('change', () => {
      isDirty = true;
      updatePreview();
      if (element.closest('.field')?.classList.contains('is-invalid')) setFieldValidity(name);
    });
    element.addEventListener('blur', () => setFieldValidity(name));
  });

  const productTypeSelect = byId('productType');
  const customTypeContainer = byId('customTypeContainer');
  const customTypeInput = byId('customProductType');
  const customTypeError = byId('customProductTypeError');

  if (productTypeSelect) {
    productTypeSelect.addEventListener('change', () => {
      if (productTypeSelect.value === 'Other') {
        if (customTypeContainer) customTypeContainer.hidden = false;
        if (customTypeInput) customTypeInput.focus();
      } else {
        if (customTypeContainer) {
          customTypeContainer.hidden = true;
          customTypeContainer.classList.remove('is-invalid');
        }
        if (customTypeInput) {
          customTypeInput.value = '';
          customTypeInput.setAttribute('aria-invalid', 'false');
        }
        if (customTypeError) customTypeError.textContent = '';
      }
      updatePreview();
    });
  }

  if (customTypeInput) {
    customTypeInput.addEventListener('input', () => {
      isDirty = true;
      updatePreview();
      if (customTypeContainer?.classList.contains('is-invalid')) {
        setFieldValidity('productType');
      }
    });

    customTypeInput.addEventListener('blur', () => {
      if (productTypeSelect?.value === 'Other') {
        setFieldValidity('productType');
      }
    });
  }

  document.querySelectorAll('.brand-option').forEach(button => {
    button.addEventListener('click', () => {
      addVariant(button.dataset.brand, button.dataset.price);
      isDirty = true;
      showToast(`${button.dataset.brand} variant added. Its final price updates live.`);
    });
  });

  const addVariantBtn = byId('addVariantButton');
  if (addVariantBtn) {
    addVariantBtn.addEventListener('click', () => addVariant());
  }

  if (form) {
    form.addEventListener('submit', async event => {
      event.preventDefault();
      const valid = Object.keys(fields).map(name => setFieldValidity(name)).every(Boolean);
      const emptyVariant = [...document.querySelectorAll('[data-variant-name]')].find(input => input.value.trim() === '');
      if (emptyVariant) {
        emptyVariant.closest('.field')?.classList.add('is-invalid');
        emptyVariant.focus();
        showToast('Give every variant a brand or configuration name.', 'error');
        return;
      }
      if (!valid) {
        if (byId('productType')?.value === 'Other' && !byId('customProductType')?.value.trim()) {
          const firstInvalid = form.querySelector('.is-invalid input, .is-invalid select, .is-invalid textarea');
          if (firstInvalid && firstInvalid !== productTypeSelect) {
            firstInvalid.focus();
          } else if (customTypeInput) {
            customTypeInput.focus();
          }
        } else {
          form.querySelector('.is-invalid input, .is-invalid select, .is-invalid textarea')?.focus();
        }
        showToast('Review the highlighted fields before saving.', 'error');
        return;
      }

      if (saveButton) {
        saveButton.disabled = true;
        saveButton.innerHTML = '<span aria-hidden="true">✓</span> Saving…';
      }

      try {
        const formData = new FormData(form);
        const actionUrl = form.getAttribute('action') || window.location.href;
        const response = await fetch(actionUrl, {
          method: 'POST',
          body: formData,
          headers: {
            'X-Requested-With': 'XMLHttpRequest',
            'Accept': 'application/json'
          }
        });

        if (response.ok) {
          const data = await response.json();
          isDirty = false;
          const variantsCount = document.querySelectorAll('.variant-row').length;
          const prodName = byId('productName')?.value.trim() || 'Product';
          showToast(data.message || `${prodName} and ${variantsCount} variant${variantsCount === 1 ? '' : 's'} are ready for your catalogue.`);
          window.setTimeout(() => {
            window.location.href = data.redirect_url || '/products/';
          }, 1100);
        } else {
          const errData = await response.json().catch(() => ({}));
          if (saveButton) {
            saveButton.disabled = false;
            saveButton.innerHTML = '<span aria-hidden="true">+</span> Save product';
          }
          if (errData.errors) {
            Object.keys(errData.errors).forEach(errKey => {
              const errEl = byId(`${errKey}Error`) || byId('variantListError') || byId('productNameError');
              if (errEl) {
                errEl.textContent = errData.errors[errKey];
                errEl.style.display = 'block';
              }
              const fld = byId(errKey);
              if (fld) {
                fld.closest('.field')?.classList.add('is-invalid');
                fld.setAttribute('aria-invalid', 'true');
              }
            });
            const firstErrField = Object.keys(errData.errors)[0];
            const firstErrEl = byId(firstErrField);
            if (firstErrEl) firstErrEl.focus();
            showToast(errData.errors[firstErrField] || 'Review the highlighted fields before saving.', 'error');
          } else {
            showToast('An error occurred while saving the product. Please try again.', 'error');
          }
        }
      } catch (err) {
        // Fallback to standard form submission if fetch is interrupted
        HTMLFormElement.prototype.submit.call(form);
      }
    });
  }

  const cancelBtn = byId('cancelButton');
  if (cancelBtn) {
    cancelBtn.addEventListener('click', () => {
      if (isDirty && !window.confirm('Discard the product details you entered?')) return;
      window.location.href = '/products/';
    });
  }

  const sidebar = byId('sidebar');
  const menuButton = byId('menuButton');
  if (menuButton && sidebar) {
    menuButton.addEventListener('click', () => {
      const open = sidebar.classList.toggle('open');
      menuButton.setAttribute('aria-expanded', String(open));
    });
  }

  updateCounters();
  updatePreview();
})();
