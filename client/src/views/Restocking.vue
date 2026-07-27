<template>
  <div class="restocking">
    <div class="page-header">
      <h2>{{ t('restocking.title') }}</h2>
      <p>{{ t('restocking.description') }}</p>
    </div>

    <div v-if="loading" class="loading">{{ t('common.loading') }}</div>
    <div v-else-if="error" class="error">{{ error }}</div>
    <div v-else>
      <!-- Budget control -->
      <div class="card budget-card">
        <div class="budget-row">
          <div class="budget-label">
            <div class="stat-label">{{ t('restocking.budgetLabel') }}</div>
            <div class="budget-value">{{ currencySymbol }}{{ formatNumber(budget) }}</div>
            <div class="budget-hint">{{ t('restocking.budgetHint') }}</div>
          </div>
          <div class="budget-slider">
            <input
              type="range"
              min="0"
              :max="maxBudget"
              :step="sliderStep"
              v-model.number="budget"
              @input="onBudgetInput"
              aria-label="budget"
            />
            <div class="budget-scale">
              <span>{{ currencySymbol }}0</span>
              <span>{{ currencySymbol }}{{ formatNumber(maxBudget) }}</span>
            </div>
          </div>
        </div>
      </div>

      <!-- Coverage summary -->
      <div class="stats-grid">
        <div class="stat-card info">
          <div class="stat-label">{{ t('restocking.spend') }}</div>
          <div class="stat-value">{{ currencySymbol }}{{ formatNumber(plan.total_cost) }}</div>
        </div>
        <div class="stat-card success">
          <div class="stat-label">{{ t('restocking.fundedItems') }}</div>
          <div class="stat-value">{{ plan.funded_items }}</div>
        </div>
        <div class="stat-card">
          <div class="stat-label">{{ t('restocking.remaining') }}</div>
          <div class="stat-value">{{ currencySymbol }}{{ formatNumber(plan.remaining_budget) }}</div>
        </div>
        <div class="stat-card warning">
          <div class="stat-label">{{ t('restocking.deferredItems') }}</div>
          <div class="stat-value">{{ plan.deferred_items }}</div>
        </div>
      </div>

      <!-- Recommendations -->
      <div class="card">
        <div class="card-header">
          <h3 class="card-title">{{ t('restocking.recommendations') }}</h3>
          <button
            class="place-order-btn"
            :disabled="!fundedRecommendations.length || placing"
            @click="placeOrder"
          >
            {{ placing ? t('restocking.placingOrder') : t('restocking.placeOrder') }}
          </button>
        </div>

        <div v-if="orderMessage" class="order-success">{{ orderMessage }}</div>

        <div v-if="!plan.recommendations.length" class="empty-state">
          {{ t('restocking.noRecommendations') }}
        </div>
        <div v-else class="table-container">
          <table>
            <thead>
              <tr>
                <th>{{ t('restocking.table.item') }}</th>
                <th>{{ t('restocking.table.warehouse') }}</th>
                <th class="num">{{ t('restocking.table.onHand') }}</th>
                <th class="num">{{ t('restocking.table.reorderPoint') }}</th>
                <th class="num">{{ t('restocking.table.need') }}</th>
                <th class="num">{{ t('restocking.table.order') }}</th>
                <th class="num">{{ t('restocking.table.unitCost') }}</th>
                <th class="num">{{ t('restocking.table.lineCost') }}</th>
                <th>{{ t('restocking.table.leadTime') }}</th>
                <th>{{ t('restocking.table.priority') }}</th>
                <th>{{ t('restocking.table.funding') }}</th>
              </tr>
            </thead>
            <tbody>
              <tr
                v-for="rec in plan.recommendations"
                :key="rec.sku"
                :class="{ 'is-deferred': rec.funding === 'deferred' }"
              >
                <td>
                  <div class="item-name">{{ translateProductName(rec.name) }}</div>
                  <div class="item-sku">{{ rec.sku }}</div>
                </td>
                <td>{{ translateWarehouse(rec.warehouse) }}</td>
                <td class="num">{{ rec.quantity_on_hand }}</td>
                <td class="num">{{ rec.reorder_point }}</td>
                <td class="num">{{ rec.deficit }}</td>
                <td class="num">
                  <strong>{{ rec.funded_quantity }}</strong>
                  <span v-if="rec.funding === 'partial'" class="of-needed">
                    {{ t('restocking.ofNeeded', { needed: rec.deficit }) }}
                  </span>
                </td>
                <td class="num">{{ currencySymbol }}{{ formatNumber(rec.unit_cost) }}</td>
                <td class="num"><strong>{{ currencySymbol }}{{ formatNumber(rec.funded_cost) }}</strong></td>
                <td>{{ t('restocking.daysLead', { days: rec.lead_time_days }) }}</td>
                <td>
                  <span :class="['badge', priorityClass(rec.priority)]">
                    {{ t('restocking.' + rec.priority) }}
                  </span>
                </td>
                <td>
                  <span :class="['funding-pill', rec.funding]">{{ fundingLabel(rec.funding) }}</span>
                </td>
              </tr>
            </tbody>
          </table>
        </div>
      </div>
    </div>
  </div>
</template>

<script>
import { ref, onMounted, watch, computed } from 'vue'
import { api } from '../api'
import { useFilters } from '../composables/useFilters'
import { useI18n } from '../composables/useI18n'

export default {
  name: 'Restocking',
  setup() {
    const { t, currentCurrency, translateProductName, translateWarehouse } = useI18n()

    const currencySymbol = computed(() => (currentCurrency.value === 'JPY' ? '¥' : '$'))

    const loading = ref(true)
    const error = ref(null)
    const placing = ref(false)
    const orderMessage = ref('')

    // budget is null until the first plan loads, then defaults to the full amount
    const budget = ref(0)
    const maxBudget = ref(0)
    const budgetInitialized = ref(false)

    const plan = ref({
      budget: 0,
      max_budget: 0,
      total_cost: 0,
      remaining_budget: 0,
      funded_items: 0,
      funded_units: 0,
      deferred_items: 0,
      recommendations: []
    })

    // Location/Category filters apply; the money-based budget is the primary control here.
    const { selectedLocation, selectedCategory, getCurrentFilters } = useFilters()

    // Slider granularity scales with the total so the control stays usable at any range.
    const sliderStep = computed(() => {
      const step = Math.max(50, Math.round(maxBudget.value / 200 / 50) * 50)
      return step || 50
    })

    const fundedRecommendations = computed(() =>
      plan.value.recommendations.filter(r => r.funded_quantity > 0)
    )

    const loadPlan = async (withBudget) => {
      try {
        error.value = null
        const filters = getCurrentFilters()
        const data = await api.getRestockRecommendations({
          budget: withBudget,
          warehouse: filters.warehouse,
          category: filters.category
        })
        plan.value = data
        maxBudget.value = data.max_budget

        // On first load (or when filters shrink the max below the current budget),
        // default the slider to fully fund everything.
        if (!budgetInitialized.value) {
          budget.value = data.max_budget
          budgetInitialized.value = true
        } else if (budget.value > data.max_budget) {
          budget.value = data.max_budget
        }
      } catch (err) {
        error.value = 'Failed to load restocking plan: ' + err.message
      } finally {
        loading.value = false
      }
    }

    // Debounce slider input so dragging doesn't fire a request per pixel.
    let budgetTimer = null
    const onBudgetInput = () => {
      orderMessage.value = ''
      clearTimeout(budgetTimer)
      budgetTimer = setTimeout(() => loadPlan(budget.value), 120)
    }

    // Reloading on filter change resets the budget baseline to the new max.
    watch([selectedLocation, selectedCategory], () => {
      budgetInitialized.value = false
      loadPlan(undefined)
    })

    const placeOrder = async () => {
      if (!fundedRecommendations.value.length) return
      try {
        placing.value = true
        orderMessage.value = ''
        const items = fundedRecommendations.value.map(r => ({
          sku: r.sku,
          quantity: r.funded_quantity
        }))
        const order = await api.createRestockOrder({ items, budget: budget.value })
        orderMessage.value = t('restocking.orderPlaced', { orderNumber: order.order_number })
      } catch (err) {
        error.value = 'Failed to place restocking order: ' + err.message
      } finally {
        placing.value = false
      }
    }

    const priorityClass = (priority) =>
      ({ high: 'high', medium: 'medium', low: 'low' })[priority] || 'low'

    const fundingLabel = (funding) =>
      ({
        funded: t('restocking.fullyFunded'),
        partial: t('restocking.partiallyFunded'),
        deferred: t('restocking.deferred')
      })[funding] || funding

    const formatNumber = (value) => {
      const locale = currentCurrency.value === 'JPY' ? 'ja-JP' : 'en-US'
      return Number(value || 0).toLocaleString(locale, { maximumFractionDigits: 2 })
    }

    onMounted(() => loadPlan(undefined))

    return {
      t,
      loading,
      error,
      placing,
      orderMessage,
      budget,
      maxBudget,
      sliderStep,
      plan,
      fundedRecommendations,
      currencySymbol,
      onBudgetInput,
      placeOrder,
      priorityClass,
      fundingLabel,
      formatNumber,
      translateProductName,
      translateWarehouse
    }
  }
}
</script>

<style scoped>
.budget-card {
  padding: 1.5rem;
}

.budget-row {
  display: grid;
  grid-template-columns: minmax(220px, 1fr) 2fr;
  gap: 2rem;
  align-items: center;
}

@media (max-width: 720px) {
  .budget-row {
    grid-template-columns: 1fr;
    gap: 1.25rem;
  }
}

.budget-value {
  font-size: 2.25rem;
  font-weight: 700;
  color: #2563eb;
  letter-spacing: -0.025em;
  margin: 0.25rem 0;
  font-variant-numeric: tabular-nums;
}

.budget-hint {
  font-size: 0.813rem;
  color: #64748b;
}

.budget-slider input[type='range'] {
  width: 100%;
  height: 6px;
  border-radius: 999px;
  appearance: none;
  -webkit-appearance: none;
  background: #e2e8f0;
  outline: none;
  cursor: pointer;
}

.budget-slider input[type='range']::-webkit-slider-thumb {
  -webkit-appearance: none;
  appearance: none;
  width: 22px;
  height: 22px;
  border-radius: 50%;
  background: #2563eb;
  border: 3px solid #ffffff;
  box-shadow: 0 1px 4px rgba(15, 23, 42, 0.25);
}

.budget-slider input[type='range']::-moz-range-thumb {
  width: 22px;
  height: 22px;
  border-radius: 50%;
  background: #2563eb;
  border: 3px solid #ffffff;
  box-shadow: 0 1px 4px rgba(15, 23, 42, 0.25);
}

.budget-scale {
  display: flex;
  justify-content: space-between;
  margin-top: 0.5rem;
  font-size: 0.75rem;
  color: #94a3b8;
  font-variant-numeric: tabular-nums;
}

.place-order-btn {
  background: #2563eb;
  color: #ffffff;
  border: none;
  border-radius: 6px;
  padding: 0.625rem 1.25rem;
  font-weight: 600;
  font-size: 0.875rem;
  cursor: pointer;
  transition: background 0.2s ease;
}

.place-order-btn:hover:not(:disabled) {
  background: #1d4ed8;
}

.place-order-btn:disabled {
  background: #cbd5e1;
  cursor: not-allowed;
}

.order-success {
  background: #d1fae5;
  border: 1px solid #a7f3d0;
  color: #065f46;
  padding: 0.75rem 1rem;
  border-radius: 8px;
  margin-bottom: 1rem;
  font-size: 0.875rem;
  font-weight: 500;
}

.empty-state {
  text-align: center;
  padding: 2.5rem;
  color: #64748b;
  font-size: 0.938rem;
}

.num {
  text-align: right;
  font-variant-numeric: tabular-nums;
}

.item-name {
  font-weight: 500;
  color: #0f172a;
}

.item-sku {
  font-size: 0.75rem;
  color: #94a3b8;
  font-family: ui-monospace, SFMono-Regular, Menlo, monospace;
}

.of-needed {
  display: block;
  font-size: 0.7rem;
  color: #94a3b8;
}

tr.is-deferred {
  opacity: 0.55;
}

.funding-pill {
  display: inline-block;
  padding: 0.2rem 0.6rem;
  border-radius: 999px;
  font-size: 0.7rem;
  font-weight: 700;
  text-transform: uppercase;
  letter-spacing: 0.03em;
}

.funding-pill.funded {
  background: #d1fae5;
  color: #065f46;
}

.funding-pill.partial {
  background: #fef3c7;
  color: #92400e;
}

.funding-pill.deferred {
  background: #f1f5f9;
  color: #64748b;
}
</style>
