/**
 * ============================================================================
 * شركة مختبر أساس للإستشارات الفنية والمختبرات الهندسية
 * ASAS LIMS - وحدة الفحوصات والحسابات الآلية المتقدمة (#tests)
 * متوافق مع كود البناء السعودي (SBC) ومواصفات ASTM و ISO/IEC 17025
 * ============================================================================
 */

(function(window, document) {
  'use strict';

  const AsasTests = {
    // قاعدة بيانات الفحوصات الجارية
    tests: [
      {
        id: 'TST-2026-0101',
        sampleId: '100018',
        project: 'مشروع مبنى سكني - بريدة',
        category: 'soil',
        testName: 'فحص بروكتور المعدل والكثافة (Modified Proctor)',
        standard: 'ASTM D1557 / SBC 303',
        status: 'in_progress',
        testedBy: 'م. حسام الدين',
        date: '2026-09-15',
        parameters: { mdd: 2.14, omc: 10.8, compaction: 97.2, requiredCompaction: 95.0, isCompliant: true },
        remarks: 'نسبة الدك 97.2% مطابقة لاشتراطات كود البناء السعودي (≥ 95%).'
      },
      {
        id: 'TST-2026-0102',
        sampleId: '100017',
        project: 'أبراج فندقية - مكة المكرمة',
        category: 'concrete',
        testName: 'مقاومة الضغط لمكعبات الخرسانة (Compressive Strength)',
        standard: 'ASTM C39 / BS EN 12390',
        status: 'approved',
        testedBy: 'م. أحمد فتحي',
        date: '2026-09-14',
        parameters: { ageDays: 28, targetGrade: 35.0, loadKn: 845.0, areaMm2: 22500, calculatedStrength: 37.55, isCompliant: true },
        remarks: 'إجهاد الكسر لعمر 28 يوم حقق 107% من الرتبة التصميمية المطلوبة.'
      },
      {
        id: 'TST-2026-0103',
        sampleId: '100016',
        project: 'طريق الكورنيش - جدة',
        category: 'asphalt',
        testName: 'استخلاص البيتومين وثبات مارشال (Marshall Test)',
        standard: 'ASTM D2172 / AASHTO T245',
        status: 'completed',
        testedBy: 'م. نبيل',
        date: '2026-09-13',
        parameters: { bitumenContent: 5.1, stabilityKn: 12.4, isCompliant: true },
        remarks: 'نسبة البيتومين وثبات مارشال مطابقة لمواصفات وزارة النقل (MOT).'
      }
    ],

    // تشغيل وتهيئة الوحدة
    init: function() {
      console.log('ASAS LIMS: Tests Engine Active.');
      this.renderTable();
      this.bindSearch();
    },

    // رسم وتحديث جدول الفحوصات داخل صفحة #tests
    renderTable: function(customList) {
      const container = document.getElementById('testsTableBody') || document.querySelector('#tests tbody');
      if (!container) return;

      const list = customList || this.tests;
      container.innerHTML = '';

      if (list.length === 0) {
        container.innerHTML = `<tr><td colspan="7" class="text-center py-6 text-slate-400 font-medium">لا توجد اختبارات تطابق البحث.</td></tr>`;
        return;
      }

      list.forEach(t => {
        const tr = document.createElement('tr');
        tr.className = 'hover:bg-slate-50 transition border-b border-slate-100 text-sm';
        tr.innerHTML = `
          <td class="py-3.5 px-4 font-black text-blue-700">${t.id}</td>
          <td class="py-3.5 px-4 font-bold text-slate-800">
            <div>${t.project}</div>
            <span class="text-xs text-slate-400 font-normal">رقم العينة: ${t.sampleId}</span>
          </td>
          <td class="py-3.5 px-4">
            <span class="text-xs font-bold text-slate-700 block">${t.testName}</span>
            <span class="text-[11px] text-slate-400">${t.standard}</span>
          </td>
          <td class="py-3.5 px-4">${this.getSummaryPill(t)}</td>
          <td class="py-3.5 px-4">${this.getStatusBadge(t.status)}</td>
          <td class="py-3.5 px-4 text-xs text-slate-600 font-semibold">${t.testedBy}</td>
          <td class="py-3.5 px-4 text-center">
            <button onclick="AsasTests.showDetails('${t.id}')" title="معاينة الحسابات" class="px-2.5 py-1 text-xs font-bold bg-blue-50 text-blue-700 hover:bg-blue-100 rounded-lg transition">
              معاينة
            </button>
            <button onclick="AsasTests.printReport('${t.id}')" title="طباعة شهادة الفحص" class="px-2.5 py-1 text-xs font-bold bg-slate-100 text-slate-700 hover:bg-slate-200 rounded-lg transition mr-1">
              تقرير
            </button>
          </td>
        `;
        container.appendChild(tr);
      });
    },

    // تنسيق بطاقة النتيجة الحسابية
    getSummaryPill: function(t) {
      if (t.category === 'soil') {
        const c = t.parameters.compaction;
        const cls = c >= 95 ? 'text-emerald-700 bg-emerald-50' : 'text-red-700 bg-red-50';
        return `<span class="text-xs font-bold px-2 py-0.5 rounded ${cls}">دك: ${c}% (MDD: ${t.parameters.mdd})</span>`;
      } else if (t.category === 'concrete') {
        const s = t.parameters.calculatedStrength;
        const cls = s >= t.parameters.targetGrade ? 'text-emerald-700 bg-emerald-50' : 'text-red-700 bg-red-50';
        return `<span class="text-xs font-bold px-2 py-0.5 rounded ${cls}">${s} MPa (مطلوب: ${t.parameters.targetGrade})</span>`;
      } else if (t.category === 'asphalt') {
        return `<span class="text-xs font-bold px-2 py-0.5 rounded text-blue-700 bg-blue-50">بيتومين: ${t.parameters.bitumenContent}% | ثبات: ${t.parameters.stabilityKn} kN</span>`;
      }
      return '-';
    },

    // شارات الحالة
    getStatusBadge: function(status) {
      switch(status) {
        case 'approved':
          return `<span class="text-xs bg-emerald-100 text-emerald-800 font-bold px-2.5 py-0.5 rounded-full">معتمد ومصادق</span>`;
        case 'completed':
          return `<span class="text-xs bg-blue-100 text-blue-800 font-bold px-2.5 py-0.5 rounded-full">منجز بانتظار الاعتماد</span>`;
        case 'in_progress':
          return `<span class="text-xs bg-amber-100 text-amber-800 font-bold px-2.5 py-0.5 rounded-full">قيد الفحص</span>`;
        case 'rejected':
          return `<span class="text-xs bg-red-100 text-red-800 font-bold px-2.5 py-0.5 rounded-full">غير مطابق</span>`;
        default:
          return `<span class="text-xs bg-slate-100 text-slate-600 font-bold px-2 py-0.5 rounded-full">${status}</span>`;
      }
    },

    // 1. محرك حسابات التربة (بروكتور ودك حقلي)
    calculateSoil: function(wetWeight, dryWeight, moldVol, maxDryDensity) {
      const moisture = dryWeight > 0 ? ((wetWeight - dryWeight) / dryWeight) * 100 : 0;
      const wetDensity = moldVol > 0 ? (wetWeight / moldVol) : 0;
      const dryDensity = (moisture + 100) > 0 ? (wetDensity / (1 + (moisture / 100))) : 0;
      const compactionRatio = maxDryDensity > 0 ? (dryDensity / maxDryDensity) * 100 : 0;

      return {
        moisturePercent: parseFloat(moisture.toFixed(2)),
        dryDensity: parseFloat(dryDensity.toFixed(3)),
        compactionPercent: parseFloat(compactionRatio.toFixed(1)),
        isCompliant: compactionRatio >= 95.0 // اشتراط كود البناء السعودي
      };
    },

    // 2. محرك حسابات الخرسانة (إجهاد الكسر)
    calculateConcrete: function(loadKn, dimensionMm, targetStrengthMpa) {
      const areaMm2 = dimensionMm * dimensionMm; // للمكعب 150x150 = 22500 مم2
      const strengthMpa = areaMm2 > 0 ? (loadKn * 1000) / areaMm2 : 0;

      return {
        areaMm2: areaMm2,
        strengthMpa: parseFloat(strengthMpa.toFixed(2)),
        achievementRate: targetStrengthMpa > 0 ? parseFloat(((strengthMpa / targetStrengthMpa) * 100).toFixed(1)) : 0,
        isCompliant: strengthMpa >= targetStrengthMpa
      };
    },

    // 3. محرك حسابات الأسفلت (مارشال والاستخلاص)
    calculateAsphalt: function(totalSampleWeight, aggWeightAfterExtraction, stabilityKn) {
      const bitumenWeight = totalSampleWeight - aggWeightAfterExtraction;
      const bitumenPercent = totalSampleWeight > 0 ? (bitumenWeight / totalSampleWeight) * 100 : 0;

      return {
        bitumenPercent: parseFloat(bitumenPercent.toFixed(2)),
        isCompliant: (bitumenPercent >= 4.5 && bitumenPercent <= 5.5) && stabilityKn >= 9.0
      };
    },

    // تفاصيل ومعاينة الفحص
    showDetails: function(testId) {
      const t = this.tests.find(x => x.id === testId);
      if (!t) return;
      alert(`شركة مختبر أساس للإستشارات الفنية والمختبرات الهندسية\n` +
            `--------------------------------------------------\n` +
            `رقم الفحص: ${t.id}\nالمشروع: ${t.project}\nنوع الاختبار: ${t.testName}\nالمعيار: ${t.standard}\n` +
            `الفني المختص: ${t.testedBy}\nالملاحظات: ${t.remarks}`);
    },

    // طباعة الشهادة والتقرير
    printReport: function(testId) {
      alert(`مختبر أساس:\nجاري إنشاء تقرير الاختبار المعتمد رقم (${testId}) متضمناً ختم الجودة ورمز QR للتحقق.`);
    },

    // ربط البحث السريع
    bindSearch: function() {
      const input = document.getElementById('testsSearch') || document.querySelector('#tests input[type="text"]');
      if (input) {
        input.addEventListener('input', (e) => {
          const val = e.target.value.toLowerCase().trim();
          const filtered = this.tests.filter(t => 
            t.id.toLowerCase().includes(val) || 
            t.project.toLowerCase().includes(val) || 
            t.testName.toLowerCase().includes(val) || 
            t.sampleId.includes(val)
          );
          this.renderTable(filtered);
        });
      }
    }
  };

  window.AsasTests = AsasTests;

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', () => AsasTests.init());
  } else {
    AsasTests.init();
  }

})(window, document);
